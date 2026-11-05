from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
import respx
from conftest import FakeTime

from beautycrawler.config import Settings
from beautycrawler.crawler.fetcher import PoliteFetcher
from beautycrawler.crawler.runner import load_spiders
from beautycrawler.crawler.spiders.xpertbeauty import XpertBeautySpider

BASE = "https://www.xpertbeauty.ro"
FIXTURES = Path(__file__).parent / "fixtures" / "xpertbeauty"
MASK = f"{BASE}/masca-de-fata-guinot-longue-vie-antirid-8ml"
OLD_BOX = (
    '<span id="old-price-149721" data-price-amount="74" data-price-type="oldPrice" '
    'class="price-wrapper "><span class="price">74,00&nbsp;LEI</span></span>'
)
PRICE_BOX = 'id="product-price-149721" data-price-amount="59.2"'


def load(name: str = "guinot_mask.html") -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def urlset(*urls: str) -> str:
    items = "".join(f"<url><loc>{u}</loc></url>" for u in urls)
    return f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}</urlset>'


@pytest.fixture
def spider() -> XpertBeautySpider:
    return XpertBeautySpider.__new__(XpertBeautySpider)  # parse_product needs no fetcher


def test_registered() -> None:
    assert load_spiders()["xpertbeauty"] is XpertBeautySpider


def test_parse_product(spider: XpertBeautySpider) -> None:
    [offer] = spider.parse_product(load(), MASK)
    assert offer.retailer == "xpertbeauty"
    assert offer.url == MASK
    assert offer.title == "Masca de fata Guinot Longue Vie +, antirid, 8ml"
    assert offer.brand == "Guinot"
    assert (offer.price_bani, offer.old_price_bani, offer.currency) == (5920, 7400, "RON")
    assert offer.in_stock is True
    assert offer.ean == "3500465080007"  # the JSON-LD mpn, a valid EAN-13
    assert offer.image_url == "https://media.xpertbeauty.ro/catalog/product/g/5/g508000.png"


def test_price_box_wins_over_analytics_price(spider: XpertBeautySpider) -> None:
    html = load().replace(PRICE_BOX, 'id="product-price-149721" data-price-amount="55"')
    [offer] = spider.parse_product(html, MASK)
    assert offer.price_bani == 5500


def test_analytics_prices_when_price_boxes_are_missing(spider: XpertBeautySpider) -> None:
    html = load().replace(OLD_BOX, "").replace(PRICE_BOX, 'id="something-else"')
    [offer] = spider.parse_product(html, MASK)
    assert (offer.price_bani, offer.old_price_bani) == (5920, 7400)  # price, price_base


def test_not_on_sale(spider: XpertBeautySpider) -> None:
    html = load().replace(OLD_BOX, "").replace('"price_base":74', '"price_base":59.2')
    [offer] = spider.parse_product(html, MASK)
    assert (offer.price_bani, offer.old_price_bani) == (5920, None)


def test_out_of_stock(spider: XpertBeautySpider) -> None:
    html = load().replace('"stock_status":true', '"stock_status":false')
    [offer] = spider.parse_product(html, MASK)
    assert offer.in_stock is False


def test_invalid_mpn_is_not_an_ean(spider: XpertBeautySpider) -> None:
    html = load().replace('"mpn": "3500465080007"', '"mpn": "G508000-X"')
    [offer] = spider.parse_product(html, MASK)
    assert offer.ean is None


@pytest.mark.parametrize(
    "html",
    [
        "<html><head></head><body><h1>Ten</h1></body></html>",  # a category page
        '<script type="text/x-magento-init">{"*": {"Evx_DataReshape/js/events": '
        '{"events": [{"event": {"name": "category_viewed"}, "products": []}]}}}</script>',
        '<script type="text/x-magento-init">{not json</script>',
    ],
)
def test_non_product_pages(spider: XpertBeautySpider, html: str) -> None:
    assert spider.parse_product(html, f"{BASE}/ten") == []


@pytest.mark.parametrize(
    ("url", "wanted"),
    [
        (f"{BASE}/sitemap/sitemap-1-1.xml", True),
        (f"{BASE}/sitemap/sitemap-1-3.xml", True),
        (f"{BASE}/sitemap.xml", True),
        (f"{BASE}/media/sitemap-1-1.xml", False),
        ("https://xpertbeauty.ro/sitemap/sitemap-1-1.xml", False),
    ],
)
def test_wanted_sitemaps(spider: XpertBeautySpider, url: str, wanted: bool) -> None:
    assert spider.is_wanted_sitemap(url) is wanted


@pytest.mark.parametrize(
    ("url", "is_product"),
    [
        (MASK, True),
        (f"{BASE}/ten", True),  # top-level category: dropped later by the parser
        (f"{BASE}/ten/exfoliere/masti", False),
        (f"{BASE}/ten/exfoliere/masti/brand-guinot", False),
        (f"{BASE}/ten?brand=guinot", False),  # filter URL
        (f"{BASE}/", False),
        (f"{BASE}/termeni.html", False),
        ("https://media.xpertbeauty.ro/masca", False),
    ],
)
def test_product_urls(spider: XpertBeautySpider, url: str, is_product: bool) -> None:
    assert spider.is_product_url(url) is is_product


@pytest.fixture
def mock() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        yield router


@pytest.fixture
async def live_spider(settings: Settings, fake_time: FakeTime) -> AsyncIterator[XpertBeautySpider]:
    async with PoliteFetcher(settings, sleep=fake_time.sleep, clock=fake_time.clock) as f:
        yield XpertBeautySpider(f)


async def test_crawl_filters_sitemap_urls(
    mock: respx.MockRouter, live_spider: XpertBeautySpider
) -> None:
    robots = "User-agent: *\nDisallow: /catalogsearch/\n"  # no Sitemap: line
    mock.get(f"{BASE}/robots.txt").mock(return_value=httpx.Response(200, text=robots))
    mock.get(f"{BASE}/sitemap/sitemap-1-1.xml").mock(
        return_value=httpx.Response(
            200, text=urlset(f"{BASE}/ten/exfoliere/masti", f"{BASE}/ten", MASK)
        )
    )
    mock.get(f"{BASE}/sitemap/sitemap-1-2.xml").mock(
        return_value=httpx.Response(200, text=urlset(MASK))
    )
    mock.get(f"{BASE}/sitemap/sitemap-1-3.xml").mock(return_value=httpx.Response(404))
    nested_category = mock.get(f"{BASE}/ten/exfoliere/masti")
    mock.get(f"{BASE}/ten").mock(
        return_value=httpx.Response(200, text="<html><body><h1>Ten</h1></body></html>")
    )
    mask = mock.get(MASK).mock(return_value=httpx.Response(200, text=load()))

    offers = [o async for o in live_spider.crawl()]

    assert [(o.url, o.price_bani, o.old_price_bani) for o in offers] == [(MASK, 5920, 7400)]
    assert mask.call_count == 1
    assert not nested_category.called
