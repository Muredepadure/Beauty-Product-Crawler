"""Multi-night crawling: adaptive pacing after 429, skipping recently seen pages,
stopping at a deadline, giving up on a rate-limited shop, and `--until`."""

from collections.abc import AsyncIterator, Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import ClassVar

import httpx
import pytest
import respx
from conftest import FakeTime

from beautycrawler.config import Settings
from beautycrawler.crawler.__main__ import deadline_from
from beautycrawler.crawler.fetcher import PoliteFetcher
from beautycrawler.crawler.spider import (
    RATE_LIMIT_GIVE_UP_AFTER,
    CrawlStats,
    JsonLdSpider,
    brand_token,
    page_key,
)

BASE = "https://night.example.ro"
PRODUCT = (Path(__file__).parent / "fixtures" / "jsonld" / "single_offer.html").read_text(
    encoding="utf-8"
)


class NightSpider(JsonLdSpider):
    slug = "night"
    name = "Night"
    base_url = BASE
    sitemap_urls: ClassVar[tuple[str, ...]] = ()

    def is_product_url(self, url: str) -> bool:
        return "/p/" in url


def urlset(*urls: str) -> str:
    items = "".join(f"<url><loc>{u}</loc></url>" for u in urls)
    return f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}</urlset>'


def site(mock: respx.MockRouter, n: int) -> list[str]:
    urls = [f"{BASE}/p/{i}" for i in range(1, n + 1)]
    robots = f"User-agent: *\nSitemap: {BASE}/sitemap.xml\n"
    mock.get(f"{BASE}/robots.txt").mock(return_value=httpx.Response(200, text=robots))
    mock.get(f"{BASE}/sitemap.xml").mock(return_value=httpx.Response(200, text=urlset(*urls)))
    return urls


@pytest.fixture
def mock() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        yield router


@pytest.fixture
async def fetcher(settings: Settings, fake_time: FakeTime) -> AsyncIterator[PoliteFetcher]:
    async with PoliteFetcher(settings, sleep=fake_time.sleep, clock=fake_time.clock) as f:
        yield f


def test_page_key_ignores_query_fragment_and_trailing_slash() -> None:
    assert page_key("https://Shop.ro/products/x/?variant=1#sku=2") == "https://shop.ro/products/x"
    assert page_key("https://shop.ro/products/x") == "https://shop.ro/products/x"


async def test_429_retry_after_slows_the_host_for_the_rest_of_the_run(
    fetcher: PoliteFetcher, mock: respx.MockRouter, fake_time: FakeTime
) -> None:
    urls = site(mock, 2)
    mock.get(urls[0]).mock(
        side_effect=[httpx.Response(429, headers={"retry-after": "60"}), httpx.Response(200)]
    )
    mock.get(urls[1]).mock(return_value=httpx.Response(200))

    await fetcher.fetch(urls[0])
    assert fetcher.host_delay("night.example.ro") == 60.0
    before = fake_time.now
    await fetcher.fetch(urls[1])
    # The next page waits a full minute, not the configured 2 s.
    assert fake_time.now - before == pytest.approx(60.0)


async def test_adaptive_delay_is_capped(fetcher: PoliteFetcher, mock: respx.MockRouter) -> None:
    urls = site(mock, 1)
    mock.get(urls[0]).mock(
        side_effect=[httpx.Response(429, headers={"retry-after": "3600"}), httpx.Response(200)]
    )
    await fetcher.fetch(urls[0])
    assert fetcher.host_delay("night.example.ro") == 120.0


async def test_skip_urls_leave_out_seen_pages_and_dont_count_towards_limit(
    fetcher: PoliteFetcher, mock: respx.MockRouter
) -> None:
    urls = site(mock, 4)
    for u in urls:
        mock.get(u).mock(return_value=httpx.Response(200, text=PRODUCT))
    spider = NightSpider(fetcher, skip_urls=frozenset({page_key(urls[0]), page_key(urls[1])}))
    stats = CrawlStats()

    fetched = [u async for u in spider.discover(limit=2)]
    assert fetched == urls[2:]  # the limit counts new pages only

    spider = NightSpider(fetcher, skip_urls=frozenset({page_key(urls[0] + "/")}))
    offers = [o async for o in spider.crawl(stats=stats)]
    assert len(offers) == 3
    assert stats.skipped_seen == 1


async def test_deadline_stops_between_pages(
    fetcher: PoliteFetcher, mock: respx.MockRouter, fake_time: FakeTime
) -> None:
    urls = site(mock, 10)
    for u in urls:
        mock.get(u).mock(return_value=httpx.Response(200, text=PRODUCT))
    # 2 s between requests: robots + sitemap + 2 pages fit before the deadline.
    spider = NightSpider(fetcher, deadline=fake_time.now + 7, clock=fake_time.clock)
    stats = CrawlStats()
    offers = [o async for o in spider.crawl(stats=stats)]
    assert 0 < len(offers) < 10
    assert stats.stopped == "time limit reached"


async def test_shop_answering_429_is_given_up_for_the_run(
    settings: Settings, fake_time: FakeTime, mock: respx.MockRouter
) -> None:
    urls = site(mock, 20)
    routes = [mock.get(u).mock(return_value=httpx.Response(429)) for u in urls]
    no_retries = settings.model_copy(update={"max_retries": 0})
    async with PoliteFetcher(no_retries, sleep=fake_time.sleep, clock=fake_time.clock) as f:
        stats = CrawlStats()
        offers = [o async for o in NightSpider(f).crawl(stats=stats)]
    assert offers == []
    assert stats.pages_fetched == RATE_LIMIT_GIVE_UP_AFTER
    assert stats.stopped is not None and stats.stopped.startswith("rate limited")
    assert sum(r.call_count for r in routes) == RATE_LIMIT_GIVE_UP_AFTER


async def test_a_successful_page_resets_the_429_count(
    settings: Settings, fake_time: FakeTime, mock: respx.MockRouter
) -> None:
    urls = site(mock, 2 * RATE_LIMIT_GIVE_UP_AFTER)
    for i, u in enumerate(urls):
        ok = i == RATE_LIMIT_GIVE_UP_AFTER - 1
        mock.get(u).mock(return_value=httpx.Response(200 if ok else 429, text=PRODUCT))
    no_retries = settings.model_copy(update={"max_retries": 0})
    async with PoliteFetcher(no_retries, sleep=fake_time.sleep, clock=fake_time.clock) as f:
        stats = CrawlStats()
        offers = [o async for o in NightSpider(f).crawl(stats=stats)]
    assert len(offers) == 1
    # 4 refused, 1 ok (reset), then 5 refused in a row: given up after all 10 pages.
    assert stats.pages_fetched == 2 * RATE_LIMIT_GIVE_UP_AFTER
    assert stats.stopped is not None


def test_deadline_from_picks_the_next_occurrence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("beautycrawler.crawler.__main__.time.monotonic", lambda: 0.0)
    tz = timezone(timedelta(hours=2))
    evening = datetime(2026, 10, 26, 23, 0, tzinfo=tz)
    assert deadline_from("07:00", now=evening) == 8 * 3600  # tomorrow morning
    morning = datetime(2026, 10, 26, 6, 30, tzinfo=tz)
    assert deadline_from("07:00", now=morning) == 30 * 60  # later today
    with pytest.raises(ValueError):
        deadline_from("soon", now=morning)


def test_brand_token_ignores_case_accents_and_punctuation() -> None:
    assert brand_token("L`OREAL PROFESSIONNEL") == "lorealprofessionnel"
    assert brand_token("Kérastase") == "kerastase"
    assert brand_token("l-oreal-serie-expert") == "lorealserieexpert"


async def test_brand_filter_skips_other_brands_before_fetching(
    fetcher: PoliteFetcher, mock: respx.MockRouter
) -> None:
    robots = f"User-agent: *\nSitemap: {BASE}/sitemap.xml\n"
    mock.get(f"{BASE}/robots.txt").mock(return_value=httpx.Response(200, text=robots))
    urls = [
        f"{BASE}/p/sampon-wella-professionals-500ml",
        f"{BASE}/p/masca-l-oreal-professionnel-250ml",
        f"{BASE}/p/kerastase-elixir-ultime",
        f"{BASE}/p/oja-opi-red",
    ]
    mock.get(f"{BASE}/sitemap.xml").mock(return_value=httpx.Response(200, text=urlset(*urls)))
    pages = [mock.get(u).mock(return_value=httpx.Response(200, text=PRODUCT)) for u in urls]

    spider = NightSpider(fetcher, brands=("Wella", "L'Oréal", "Kerastase"))
    assert [u async for u in spider.discover()] == urls[:3]
    assert spider.skipped_brands == 1
    assert not pages[3].called  # the OPI page is never requested


async def test_brand_filter_drops_offers_of_another_brand(
    fetcher: PoliteFetcher, mock: respx.MockRouter
) -> None:
    # The URL names Wella, but the page's brand (La Roche-Posay) doesn't: dropped.
    robots = f"User-agent: *\nSitemap: {BASE}/sitemap.xml\n"
    mock.get(f"{BASE}/robots.txt").mock(return_value=httpx.Response(200, text=robots))
    url = f"{BASE}/p/accesoriu-compatibil-wella"
    mock.get(f"{BASE}/sitemap.xml").mock(return_value=httpx.Response(200, text=urlset(url)))
    mock.get(url).mock(return_value=httpx.Response(200, text=PRODUCT))
    stats = CrawlStats()
    offers = [o async for o in NightSpider(fetcher, brands=("wella",)).crawl(stats=stats)]
    assert offers == []
    assert stats.skipped_brands == 1
    # Without a filter the same page gives its offer.
    assert len([o async for o in NightSpider(fetcher).crawl()]) == 1
