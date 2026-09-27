from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
import respx
from conftest import FakeTime

from beautycrawler.config import Settings
from beautycrawler.crawler.fetcher import PoliteFetcher
from beautycrawler.crawler.runner import load_spiders
from beautycrawler.crawler.spiders.parfimo import ParfimoSpider

BASE = "https://www.parfimo.ro"
FIXTURES = Path(__file__).parent / "fixtures" / "parfimo"
GEL = f"{BASE}/la-roche-posay-effaclar-cleansing-gel-200-ml_z584857/"
MICELLAR = f"{BASE}/la-roche-posay-effaclar-apa-micelara-200-ml_z584859/"


def load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def urlset(*urls: str) -> str:
    items = "".join(f"<url><loc>{u}</loc></url>" for u in urls)
    return f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}</urlset>'


def index(*paths: str) -> str:
    items = "".join(f"<sitemap><loc>{BASE}{p}</loc></sitemap>" for p in paths)
    return (
        f'<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}</sitemapindex>'
    )


@pytest.fixture
def spider() -> ParfimoSpider:
    return ParfimoSpider.__new__(ParfimoSpider)  # parse_product needs no fetcher


def test_registered() -> None:
    assert load_spiders()["parfimo"] is ParfimoSpider


def test_parse_product(spider: ParfimoSpider) -> None:
    [offer] = spider.parse_product(load("effaclar_cleansing_gel.html"), GEL)
    assert offer.retailer == "parfimo"
    assert offer.url == GEL
    assert offer.title == "La Roche-Posay Effaclar Cleansing gel 200 ml"
    assert offer.brand == "La Roche-Posay"
    assert (offer.price_bani, offer.old_price_bani, offer.currency) == (6200, None, "RON")
    assert offer.in_stock is True
    assert offer.ean == "3337872411083"
    # Not in the JSON-LD: taken from the product heading and the gallery.
    assert offer.image_url == (
        "https://data.parfimo.ro/photo/product_detail/126088/photo.desktop.ro?1789644435"
    )


def test_parse_diacritics(spider: ParfimoSpider) -> None:
    [offer] = spider.parse_product(load("effaclar_micellar_water.html"), MICELLAR)
    assert offer.title == "La Roche-Posay Effaclar apă micelară 200 ml"
    assert (offer.price_bani, offer.ean) == (6100, "3433422408357")
    assert offer.brand == "La Roche-Posay"


def test_non_product_page(spider: ParfimoSpider) -> None:
    assert spider.parse_product("<html><head></head><body>Parfumuri</body></html>", BASE) == []


def test_missing_heading_and_gallery_leave_brand_and_image_empty(spider: ParfimoSpider) -> None:
    html = load("effaclar_cleansing_gel.html").split("<body>")[0] + "<body></body></html>"
    [offer] = spider.parse_product(html, GEL)
    assert (offer.brand, offer.image_url) == (None, None)


@pytest.mark.parametrize(
    ("url", "wanted"),
    [
        (f"{BASE}/sitemap.xml", True),
        (f"{BASE}/1/sitemap_products.xml", True),
        (f"{BASE}/7/sitemap_products.xml", True),
        (f"{BASE}/sitemap_products_sections.xml", False),
        (f"{BASE}/sitemap_producers.xml", False),
        (f"{BASE}/sitemap_articles.xml", False),
        (f"{BASE}/sitemap_indexed_filter_variations.xml", False),
        ("https://cdn.example.com/1/sitemap_products.xml", False),
    ],
)
def test_wanted_sitemaps(spider: ParfimoSpider, url: str, wanted: bool) -> None:
    assert spider.is_wanted_sitemap(url) is wanted


@pytest.mark.parametrize(
    ("url", "is_product"),
    [
        (GEL, True),
        (f"{BASE}/calvin-klein-escape-for-men-apa-de-toaleta-pentru-barbati-50-ml_z26/", True),
        (f"{BASE}/la-roche-posay/", False),  # producer page
        (f"{BASE}/ingrijire-ten/", False),  # category
        (f"{BASE}/", False),
        ("https://parfimo.ro/la-roche-posay-effaclar-cleansing-gel-200-ml_z584857/", False),
    ],
)
def test_product_urls(spider: ParfimoSpider, url: str, is_product: bool) -> None:
    assert spider.is_product_url(url) is is_product


@pytest.fixture
def mock() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        yield router


@pytest.fixture
async def live_spider(settings: Settings, fake_time: FakeTime) -> AsyncIterator[ParfimoSpider]:
    async with PoliteFetcher(settings, sleep=fake_time.sleep, clock=fake_time.clock) as f:
        yield ParfimoSpider(f)


async def test_crawl_uses_only_product_sitemaps(
    mock: respx.MockRouter, live_spider: ParfimoSpider
) -> None:
    robots = f"User-agent: *\nDisallow: /schimbare-date/\nSitemap: {BASE}/sitemap.xml\n"
    mock.get(f"{BASE}/robots.txt").mock(return_value=httpx.Response(200, text=robots))
    mock.get(f"{BASE}/sitemap.xml").mock(
        return_value=httpx.Response(
            200,
            text=index(
                "/sitemap_articles.xml",
                "/sitemap_producers.xml",
                "/1/sitemap_products.xml",
                "/2/sitemap_products.xml",
            ),
        )
    )
    skipped = [
        mock.get(f"{BASE}/sitemap_articles.xml"),
        mock.get(f"{BASE}/sitemap_producers.xml"),
    ]
    mock.get(f"{BASE}/1/sitemap_products.xml").mock(
        return_value=httpx.Response(200, text=urlset(GEL, f"{BASE}/la-roche-posay/"))
    )
    mock.get(f"{BASE}/2/sitemap_products.xml").mock(
        return_value=httpx.Response(200, text=urlset(MICELLAR))
    )
    mock.get(GEL).mock(return_value=httpx.Response(200, text=load("effaclar_cleansing_gel.html")))
    mock.get(MICELLAR).mock(
        return_value=httpx.Response(200, text=load("effaclar_micellar_water.html"))
    )

    offers = [o async for o in live_spider.crawl()]

    assert [(o.url, o.price_bani) for o in offers] == [(GEL, 6200), (MICELLAR, 6100)]
    assert not any(route.called for route in skipped)
