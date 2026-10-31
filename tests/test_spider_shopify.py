from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
import respx
from conftest import FakeTime

from beautycrawler.config import Settings
from beautycrawler.crawler.fetcher import PoliteFetcher
from beautycrawler.crawler.runner import load_spiders
from beautycrawler.crawler.shopify import ShopifySpider
from beautycrawler.crawler.spiders.beautylounge import BeautyLoungeSpider
from beautycrawler.crawler.spiders.probeauty import ProBeautySpider

FIXTURES = Path(__file__).parent / "fixtures"
PROBEAUTY = "https://probeauty.ro"
LOUNGE = "https://beauty-lounge.ro"
IRON = f"{PROBEAUTY}/products/babyliss-pro-dial-a-heat-iron-32mm"
JOICO = (
    f"{LOUNGE}/products/tratament-de-par-joico-k-pak-intense-hydrator-"
    "hidratare-intensiva-pentru-par-deteriorat-250ml"
)
JOICO_NAME = (
    "Joico Tratament de par K-Pak Intense Hydrator 250ml Tratament Intensiv Pentru Par Deteriora"
)


def load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def urlset(*urls: str) -> str:
    items = "".join(f"<url><loc>{u}</loc></url>" for u in urls)
    return f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}</urlset>'


def index(*urls: str) -> str:
    items = "".join(f"<sitemap><loc>{u}</loc></sitemap>" for u in urls)
    return (
        f'<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}</sitemapindex>'
    )


@pytest.fixture
def probeauty() -> ProBeautySpider:
    return ProBeautySpider.__new__(ProBeautySpider)  # parse_product needs no fetcher


@pytest.fixture
def lounge() -> BeautyLoungeSpider:
    return BeautyLoungeSpider.__new__(BeautyLoungeSpider)


def test_registered() -> None:
    spiders = load_spiders()
    assert spiders["probeauty"] is ProBeautySpider
    assert spiders["beautylounge"] is BeautyLoungeSpider
    assert issubclass(ProBeautySpider, ShopifySpider)
    assert issubclass(BeautyLoungeSpider, ShopifySpider)


def test_parse_probeauty(probeauty: ProBeautySpider) -> None:
    [offer] = probeauty.parse_product(load("probeauty/curling_iron.html"), IRON)
    assert offer.retailer == "probeauty"
    assert offer.url == f"{IRON}?variant=49799327973642"  # the variant's own offer URL
    assert offer.title == "BaByliss PRO Dial-a-Heat Ondulator 32 mm"
    assert offer.brand == "BaByliss PRO"
    assert (offer.price_bani, offer.old_price_bani, offer.currency) == (21595, None, "RON")
    assert offer.in_stock is True
    assert offer.ean == "3030050091724"
    assert offer.image_url is not None
    assert offer.image_url.startswith(f"{PROBEAUTY}/cdn/shop/files/ondulator-de-par-babyliss")


def test_parse_beauty_lounge_sale_out_of_stock(lounge: BeautyLoungeSpider) -> None:
    [offer] = lounge.parse_product(load("beautylounge/joico_treatment.html"), JOICO)
    assert offer.retailer == "beautylounge"
    assert offer.url == JOICO
    # The shop itself cuts this name short in both the JSON-LD and the <h1>.
    assert offer.title == JOICO_NAME
    assert offer.brand == "Joico"
    assert (offer.price_bani, offer.old_price_bani) == (6300, 14700)
    assert offer.in_stock is False
    assert offer.ean == "074469517355"


def test_longer_heading_completes_a_cut_short_name(lounge: BeautyLoungeSpider) -> None:
    html = load("beautylounge/joico_treatment.html").replace(
        f">{JOICO_NAME}", f">\n  {JOICO_NAME}t   250 ml\n"
    )
    [offer] = lounge.parse_product(html, JOICO)
    assert offer.title == f"{JOICO_NAME}t 250 ml"


def test_unrelated_heading_does_not_replace_the_name(probeauty: ProBeautySpider) -> None:
    html = load("probeauty/curling_iron.html")
    html = html.replace("<body>", "<body><h1>Promoții de toamnă la toate ondulatoarele</h1>", 1)
    [offer] = probeauty.parse_product(html, IRON)
    assert offer.title == "BaByliss PRO Dial-a-Heat Ondulator 32 mm"


def test_non_product_page(probeauty: ProBeautySpider) -> None:
    html = "<html><head></head><body><h1>Ondulatoare</h1></body></html>"
    assert probeauty.parse_product(html, f"{PROBEAUTY}/collections/ondulatoare") == []


@pytest.mark.parametrize(
    ("url", "wanted"),
    [
        (f"{PROBEAUTY}/sitemap.xml", True),
        (f"{PROBEAUTY}/sitemap_products_1.xml?from=1&to=999", True),
        (f"{PROBEAUTY}/sitemap_products_12.xml", True),
        (f"{PROBEAUTY}/sitemap_pages_1.xml", False),
        (f"{PROBEAUTY}/sitemap_collections_1.xml", False),
        (f"{PROBEAUTY}/sitemap_blogs_1.xml", False),
        (f"{PROBEAUTY}/en/sitemap.xml", False),
        (f"{LOUNGE}/sitemap_products_1.xml", False),  # another shop
    ],
)
def test_wanted_sitemaps(probeauty: ProBeautySpider, url: str, wanted: bool) -> None:
    assert probeauty.is_wanted_sitemap(url) is wanted


@pytest.mark.parametrize(
    ("url", "is_product"),
    [
        (IRON, True),
        (f"{IRON}/", True),
        (f"https://www.probeauty.ro/products/{IRON.rsplit('/', 1)[1]}", True),
        (f"{PROBEAUTY}/en/products/babyliss-pro-dial-a-heat-iron-32mm", False),
        (f"{PROBEAUTY}/collections/ondulatoare", False),
        (f"{PROBEAUTY}/collections/ondulatoare/products/x", False),
        (f"{PROBEAUTY}/products/", False),
        (f"{PROBEAUTY}/", False),
        (f"{LOUNGE}/products/x", False),
    ],
)
def test_product_urls(probeauty: ProBeautySpider, url: str, is_product: bool) -> None:
    assert probeauty.is_product_url(url) is is_product


@pytest.fixture
def mock() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        yield router


@pytest.fixture
async def live_lounge(settings: Settings, fake_time: FakeTime) -> AsyncIterator[BeautyLoungeSpider]:
    async with PoliteFetcher(settings, sleep=fake_time.sleep, clock=fake_time.clock) as f:
        yield BeautyLoungeSpider(f)


async def test_crawl_uses_only_product_sitemaps(
    mock: respx.MockRouter, live_lounge: BeautyLoungeSpider
) -> None:
    robots = (
        "User-agent: *\nDisallow: /cart\nDisallow: /checkout\n"
        "Disallow: /collections/*+*\nSitemap: https://beauty-lounge.ro/sitemap.xml\n"
    )
    mock.get(f"{LOUNGE}/robots.txt").mock(return_value=httpx.Response(200, text=robots))
    mock.get(f"{LOUNGE}/sitemap.xml").mock(
        return_value=httpx.Response(
            200,
            text=index(
                f"{LOUNGE}/sitemap_products_1.xml?from=1&amp;to=99",
                f"{LOUNGE}/sitemap_pages_1.xml",
                f"{LOUNGE}/sitemap_collections_1.xml",
                f"{LOUNGE}/sitemap_products_2.xml?from=100&amp;to=199",
            ),
        )
    )
    skipped = [
        mock.get(f"{LOUNGE}/sitemap_pages_1.xml"),
        mock.get(f"{LOUNGE}/sitemap_collections_1.xml"),
    ]
    mock.get(f"{LOUNGE}/sitemap_products_1.xml", params={"from": "1", "to": "99"}).mock(
        return_value=httpx.Response(200, text=urlset(f"{LOUNGE}/", JOICO))
    )
    mock.get(f"{LOUNGE}/sitemap_products_2.xml", params={"from": "100", "to": "199"}).mock(
        return_value=httpx.Response(200, text=urlset(JOICO))  # duplicates are fetched once
    )
    page = mock.get(JOICO).mock(
        return_value=httpx.Response(200, text=load("beautylounge/joico_treatment.html"))
    )

    offers = [o async for o in live_lounge.crawl()]

    assert [(o.url, o.price_bani) for o in offers] == [(JOICO, 6300)]
    assert page.call_count == 1
    assert not any(route.called for route in skipped)
