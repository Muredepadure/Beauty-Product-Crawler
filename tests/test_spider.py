import gzip
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import ClassVar

import httpx
import pytest
import respx
from conftest import FakeTime

from beautycrawler.config import Settings
from beautycrawler.crawler.fetcher import PoliteFetcher
from beautycrawler.crawler.scraped import ScrapedOffer
from beautycrawler.crawler.spider import (
    CrawlStats,
    JsonLdSpider,
    Spider,
    get_spider,
    register,
    registered_spiders,
)

BASE = "https://shop.example.ro"
FIXTURES = Path(__file__).parent / "fixtures" / "jsonld"


def urlset(*urls: str) -> str:
    items = "".join(f"<url><loc>{u}</loc></url>" for u in urls)
    return f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}</urlset>'


def index(*urls: str) -> str:
    items = "".join(f"<sitemap><loc>{u}</loc></sitemap>" for u in urls)
    return (
        f'<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}</sitemapindex>'
    )


class ExampleSpider(JsonLdSpider):
    slug = "example"
    name = "Example"
    base_url = BASE
    sitemap_urls: ClassVar[tuple[str, ...]] = (f"{BASE}/extra-sitemap.xml",)

    def is_product_url(self, url: str) -> bool:
        return "/p/" in url


@pytest.fixture
def mock() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        yield router


@pytest.fixture
async def spider(settings: Settings, fake_time: FakeTime) -> AsyncIterator[ExampleSpider]:
    async with PoliteFetcher(settings, sleep=fake_time.sleep, clock=fake_time.clock) as f:
        yield ExampleSpider(f)


def site(mock: respx.MockRouter) -> respx.Route:
    """Mock a small site; returns the route of the gzipped sitemap."""
    robots = f"User-agent: *\nDisallow: /cos\nSitemap: {BASE}/sitemap_index.xml\n"
    mock.get(f"{BASE}/robots.txt").mock(return_value=httpx.Response(200, text=robots))
    mock.get(f"{BASE}/sitemap_index.xml").mock(
        return_value=httpx.Response(
            200, text=index(f"{BASE}/sm-1.xml", f"{BASE}/sm-2.xml.gz", f"{BASE}/sm-1.xml")
        )
    )
    mock.get(f"{BASE}/sm-1.xml").mock(
        return_value=httpx.Response(
            200, text=urlset(f"{BASE}/p/1", f"{BASE}/categorie/ten", f"{BASE}/p/2")
        )
    )
    gz = mock.get(f"{BASE}/sm-2.xml.gz").mock(
        return_value=httpx.Response(
            200, content=gzip.compress(urlset(f"{BASE}/p/2", f"{BASE}/p/3").encode())
        )
    )
    mock.get(f"{BASE}/extra-sitemap.xml").mock(
        return_value=httpx.Response(200, text=urlset(f"{BASE}/p/4"))
    )
    return gz


async def collect(it: AsyncIterator[str]) -> list[str]:
    return [x async for x in it]


async def test_discover_from_robots_and_extra_sitemaps(
    spider: ExampleSpider, mock: respx.MockRouter
) -> None:
    site(mock)
    urls = await collect(spider.discover())
    # category page filtered out, duplicates dropped, gz sitemap read, extra sitemap last
    assert urls == [f"{BASE}/p/1", f"{BASE}/p/2", f"{BASE}/p/3", f"{BASE}/p/4"]


async def test_discover_limit_stops_early(spider: ExampleSpider, mock: respx.MockRouter) -> None:
    gz_sitemap = site(mock)
    assert await collect(spider.discover(limit=2)) == [f"{BASE}/p/1", f"{BASE}/p/2"]
    assert not gz_sitemap.called  # never needed


async def test_discover_survives_broken_sitemaps(
    spider: ExampleSpider, mock: respx.MockRouter
) -> None:
    site(mock)
    mock.get(f"{BASE}/sm-1.xml").mock(return_value=httpx.Response(404))
    mock.get(f"{BASE}/sm-2.xml.gz").mock(return_value=httpx.Response(200, text="<html>oops"))
    assert await collect(spider.discover()) == [f"{BASE}/p/4"]


async def test_discover_skips_robots_disallowed_sitemap(
    spider: ExampleSpider, mock: respx.MockRouter
) -> None:
    robots = f"User-agent: *\nDisallow: /private\nSitemap: {BASE}/private/sm.xml\n"
    mock.get(f"{BASE}/robots.txt").mock(return_value=httpx.Response(200, text=robots))
    private = mock.get(f"{BASE}/private/sm.xml").mock(return_value=httpx.Response(200))
    mock.get(f"{BASE}/extra-sitemap.xml").mock(
        return_value=httpx.Response(200, text=urlset(f"{BASE}/p/9"))
    )
    assert await collect(spider.discover()) == [f"{BASE}/p/9"]
    assert not private.called


async def test_crawl_parses_pages_and_counts_problems(
    spider: ExampleSpider, mock: respx.MockRouter
) -> None:
    site(mock)
    product_html = (FIXTURES / "single_offer.html").read_text(encoding="utf-8")
    mock.get(f"{BASE}/p/1").mock(return_value=httpx.Response(200, text=product_html))
    mock.get(f"{BASE}/p/2").mock(return_value=httpx.Response(404))
    mock.get(f"{BASE}/p/3").mock(return_value=httpx.Response(200, text="<html>no data</html>"))
    mock.get(f"{BASE}/p/4").mock(side_effect=httpx.ConnectError("down"))

    stats = CrawlStats()
    offers = [o async for o in spider.crawl(stats=stats)]

    assert [(o.retailer, o.price_bani, o.ean) for o in offers] == [
        ("example", 8999, "3337875598996")
    ]
    assert stats.pages_fetched == 3
    assert stats.offers == 1
    assert stats.pages_without_offers == 1
    assert len(stats.errors) == 2
    assert any("HTTP 404" in e for e in stats.errors)
    assert any("ConnectError" in e for e in stats.errors)


async def test_crawl_survives_parser_exceptions(
    settings: Settings, fake_time: FakeTime, mock: respx.MockRouter
) -> None:
    class Buggy(ExampleSpider):
        def parse_product(self, html: str, url: str) -> list[ScrapedOffer]:
            if url.endswith("/p/1"):
                raise RuntimeError("selector changed")
            return super().parse_product(html, url)

    site(mock)
    html = (FIXTURES / "single_offer.html").read_text(encoding="utf-8")
    mock.get(url__regex=rf"{BASE}/p/\d").mock(return_value=httpx.Response(200, text=html))
    stats = CrawlStats()
    async with PoliteFetcher(settings, sleep=fake_time.sleep, clock=fake_time.clock) as f:
        offers = [o async for o in Buggy(f).crawl(limit=2, stats=stats)]
    assert len(offers) == 1
    assert stats.errors == [f"{BASE}/p/1: parse error: RuntimeError('selector changed')"]


def test_parse_product_is_pure_and_uses_jsonld(settings: Settings) -> None:
    spider = ExampleSpider(PoliteFetcher(settings))
    html = (FIXTURES / "variants.html").read_text(encoding="utf-8")
    offers = spider.parse_product(html, f"{BASE}/bioderma")
    assert [o.price_bani for o in offers] == [5490, 7990]


def test_spider_is_abstract(settings: Settings) -> None:
    with pytest.raises(TypeError):
        Spider(PoliteFetcher(settings))  # type: ignore[abstract]


def test_registry() -> None:
    @register
    class RegSpider(JsonLdSpider):
        slug = "test-registry"
        name = "Registry test"
        base_url = "https://reg.example.ro"

    assert get_spider("test-registry") is RegSpider
    assert "test-registry" in registered_spiders()
    assert register(RegSpider) is RegSpider  # re-registering the same class is fine

    class Clash(JsonLdSpider):
        slug = "test-registry"
        name = "Clash"
        base_url = "https://clash.example.ro"

    with pytest.raises(ValueError, match="duplicate"):
        register(Clash)
    with pytest.raises(KeyError, match="unknown spider"):
        get_spider("nope")
