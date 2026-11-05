from collections.abc import AsyncIterator, Callable, Iterator
from itertools import pairwise
from pathlib import Path

import httpx
import pytest
import respx
from conftest import FakeTime

from beautycrawler.config import Settings
from beautycrawler.crawler.fetcher import PoliteFetcher
from beautycrawler.crawler.runner import load_spiders
from beautycrawler.crawler.spiders.profihairshop import (
    ProfihairshopSpider,
    parse_brand_page,
)

BASE = "https://www.profihairshop.ro"
APEX = "https://profihairshop.ro"
FIXTURES = Path(__file__).parent / "fixtures" / "profihairshop"
# The URLs the fixtures were fetched from; the JSON-LD gives the canonical URL.
SLUG = "oro-therapy-color-keratin-vopsea-permanenta-6-3-blond-inchis-auriu-100-ml"
DYE = f"{BASE}/par/vopsele-oxidanti/{SLUG}"
DYE_CANONICAL = f"{BASE}/par/vopsele-oxidanti/Vopsea-permanenta/{SLUG}"
GIFT = f"{BASE}/seturi-cadou/idc-institute-scented-bath-rose-set-cadou-baie-cadita-mini-2-piese"
ROBOTS = f"User-agent: *\nDisallow:\nCrawl-delay: 10\nSitemap: {BASE}/sitemap-index.xml\n"


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


def redirect(to: str) -> httpx.Response:
    return httpx.Response(301, headers={"Location": to})


@pytest.fixture
def spider() -> ProfihairshopSpider:
    return ProfihairshopSpider.__new__(ProfihairshopSpider)  # parse_product needs no fetcher


def test_registered() -> None:
    assert load_spiders()["profihairshop"] is ProfihairshopSpider


def test_parse_hair_dye(spider: ProfihairshopSpider) -> None:
    [offer] = spider.parse_product(load("hair_dye.html"), DYE)
    assert offer.retailer == "profihairshop"
    assert offer.url == DYE_CANONICAL
    assert offer.title == (
        "ORO THERAPY COLOR KERATIN Vopsea permanenta 6.3 blond inchis auriu 100 ML"
    )
    assert offer.brand == "ORO THERAPY"
    assert (offer.price_bani, offer.old_price_bani, offer.currency) == (5790, None, "RON")
    assert offer.in_stock is True
    assert offer.ean == "8032947864461"
    assert offer.image_url == (
        f"{BASE}/uploads/products/"
        "oro-therapy-color-keratin-vopsea-permanenta-63-blond-inchis-auriu-100-ml_6014_1_1528383451.jpg"
    )


def test_parse_gift_set(spider: ProfihairshopSpider) -> None:
    [offer] = spider.parse_product(load("gift_set.html"), GIFT)
    assert offer.url == GIFT
    assert offer.title == "IDC Institute Scented Bath Rose Set cadou baie cadita mini 2 piese"
    assert offer.brand == "IDC Institute"
    assert (offer.price_bani, offer.in_stock, offer.ean) == (3490, True, "8436609399511")


def test_non_product_page(spider: ProfihairshopSpider) -> None:
    assert spider.parse_product("<html><head></head><body>Par</body></html>", BASE) == []


@pytest.mark.parametrize(
    ("url", "wanted"),
    [
        (f"{BASE}/sitemap-index.xml", True),
        (f"{BASE}/products-sitemap.xml", True),
        (f"{APEX}/products-sitemap.xml", True),
        (f"{BASE}/pages-sitemap.xml", False),
        (f"{BASE}/categories-sitemap.xml", False),
        (f"{BASE}/brands-sitemap.xml", False),
        ("https://cdn.example.com/products-sitemap.xml", False),
    ],
)
def test_wanted_sitemaps(spider: ProfihairshopSpider, url: str, wanted: bool) -> None:
    assert spider.is_wanted_sitemap(url) is wanted


@pytest.mark.parametrize(
    ("url", "is_product"),
    [
        (DYE, True),
        (GIFT, True),
        (f"{APEX}/seturi-cadou/set", True),
        (f"{BASE}/", False),
        (BASE, False),
        ("https://www.example.com/seturi-cadou/set", False),
    ],
)
def test_product_urls(spider: ProfihairshopSpider, url: str, is_product: bool) -> None:
    assert spider.is_product_url(url) is is_product


@pytest.fixture
def mock() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        yield router


@pytest.fixture
async def live_spider(
    settings: Settings, fake_time: FakeTime
) -> AsyncIterator[ProfihairshopSpider]:
    async with PoliteFetcher(settings, sleep=fake_time.sleep, clock=fake_time.clock) as f:
        yield ProfihairshopSpider(f)


async def test_crawl_uses_only_the_products_sitemap_and_honours_crawl_delay(
    mock: respx.MockRouter, live_spider: ProfihairshopSpider, fake_time: FakeTime
) -> None:
    requested_at: list[tuple[str, float]] = []

    def serve(body: str) -> Callable[[httpx.Request], httpx.Response]:
        def respond(request: httpx.Request) -> httpx.Response:
            requested_at.append((request.url.path, fake_time.now))
            return httpx.Response(200, text=body)

        return respond

    mock.get(f"{BASE}/robots.txt").mock(side_effect=serve(ROBOTS))
    mock.get(f"{BASE}/brands-sitemap.xml").mock(side_effect=serve(urlset()))
    mock.get(f"{BASE}/sitemap-index.xml").mock(
        side_effect=serve(
            index(
                f"{BASE}/pages-sitemap.xml",
                f"{BASE}/categories-sitemap.xml",
                f"{BASE}/products-sitemap.xml",
            )
        )
    )
    skipped = [
        mock.get(f"{BASE}/pages-sitemap.xml"),
        mock.get(f"{BASE}/categories-sitemap.xml"),
    ]
    mock.get(f"{BASE}/products-sitemap.xml").mock(side_effect=serve(urlset(DYE, GIFT)))
    mock.get(DYE).mock(side_effect=serve(load("hair_dye.html")))
    mock.get(GIFT).mock(side_effect=serve(load("gift_set.html")))

    offers = [o async for o in live_spider.crawl()]

    assert [(o.url, o.price_bani) for o in offers] == [(DYE_CANONICAL, 5790), (GIFT, 3490)]
    assert not any(route.called for route in skipped)
    # robots.txt, brands sitemap, index, products sitemap, two pages: after robots.txt,
    # every request to the host waits for the site's Crawl-delay (10 s), not our 2 s default.
    times = [t for _, t in requested_at]
    assert len(times) == 6
    assert [b - a for a, b in pairwise(times)] == [10.0] * 5


async def test_apex_domain_redirects_to_www(
    mock: respx.MockRouter, live_spider: ProfihairshopSpider
) -> None:
    # robots.txt and sitemaps listed on the apex domain redirect to www.
    mock.get(f"{BASE}/robots.txt").mock(return_value=httpx.Response(200, text=ROBOTS))
    mock.get(f"{APEX}/robots.txt").mock(return_value=redirect(f"{BASE}/robots.txt"))
    mock.get(f"{BASE}/brands-sitemap.xml").mock(return_value=httpx.Response(200, text=urlset()))
    mock.get(f"{BASE}/sitemap-index.xml").mock(
        return_value=httpx.Response(200, text=index(f"{APEX}/products-sitemap.xml"))
    )
    mock.get(f"{APEX}/products-sitemap.xml").mock(
        return_value=redirect(f"{BASE}/products-sitemap.xml")
    )
    mock.get(f"{BASE}/products-sitemap.xml").mock(
        return_value=httpx.Response(200, text=urlset(f"{APEX}/seturi-cadou/idc"))
    )
    mock.get(f"{APEX}/seturi-cadou/idc").mock(return_value=redirect(GIFT))
    mock.get(GIFT).mock(return_value=httpx.Response(200, text=load("gift_set.html")))

    offers = [o async for o in live_spider.crawl()]

    assert [(o.url, o.price_bani) for o in offers] == [(GIFT, 3490)]
    assert await live_spider.fetcher.crawl_delay(f"{APEX}/seturi-cadou/idc") == 10.0


def test_page_key_ignores_the_category_path() -> None:
    spider = ProfihairshopSpider.__new__(ProfihairshopSpider)
    sitemap = "https://www.profihairshop.ro/copii/martinelia-magic-ballet-set-manichiura-copii-5652"
    stored = (
        "https://www.profihairshop.ro/copii/seturi-manichiura/"
        "martinelia-magic-ballet-set-manichiura-copii-5652"
    )
    assert spider.page_key(sitemap) == spider.page_key(stored)
    assert spider.page_key(sitemap) != spider.page_key(
        "https://www.profihairshop.ro/copii/martinelia-magic-ballet-set-manichiura-mini-copii"
    )


# --- discovery through the brand pages (the products sitemap is out of date) -----------

WELLA = f"{BASE}/marci/wella-professionals"
ORLY = f"{BASE}/marci/orly"


def card(path: str) -> str:
    return f'<div class="product-card"><h3><a href="{path}">x</a></h3></div>'


def page_links(brand: str, *numbers: int) -> str:
    return "".join(f'<a href="/marci/{brand}?page={n}&per-page=24">{n}</a>' for n in numbers)


def serve_brands(mock: respx.MockRouter) -> list[respx.Route]:
    mock.get(f"{BASE}/robots.txt").mock(return_value=httpx.Response(200, text=ROBOTS))
    mock.get(f"{BASE}/brands-sitemap.xml").mock(
        return_value=httpx.Response(200, text=urlset(WELLA, ORLY))
    )
    routes = []
    for url, number, body in (
        # A card without the brand in its slug, and a repeat of the same product.
        (WELLA, 1, card("/par/a-1") + card("/par/noname-2") + page_links("wella-professionals", 2)),
        (
            WELLA,
            2,
            card("/par/other/a-1") + card("/par/a-3") + page_links("wella-professionals", 1),
        ),
        (ORLY, 1, card("/par/orly-4")),
    ):
        routes.append(
            mock.get(url, params={"page": str(number), "per-page": "24"}).mock(
                return_value=httpx.Response(200, text=body)
            )
        )
    return routes


def test_parse_brand_page() -> None:
    url = f"{WELLA}?page=8&per-page=24"
    urls, last = parse_brand_page(load("brand_page.html"), url)
    assert len(urls) == 3
    assert urls[0].startswith(f"{BASE}/par/ingrijirea-parului/")
    assert last == 8  # the sort link's page=99 doesn't count, nor do navigation links
    assert parse_brand_page("<html></html>", url) == ([], 1)


async def test_brand_filter_walks_only_those_brand_pages(
    settings: Settings, fake_time: FakeTime, mock: respx.MockRouter
) -> None:
    routes = serve_brands(mock)
    products_sitemap = mock.get(f"{BASE}/sitemap-index.xml")
    async with PoliteFetcher(settings, sleep=fake_time.sleep, clock=fake_time.clock) as f:
        spider = ProfihairshopSpider(f, brands=("wella",))
        urls = [u async for u in spider.discover()]
    assert urls == [f"{BASE}/par/a-1", f"{BASE}/par/noname-2", f"{BASE}/par/a-3"]
    assert not routes[2].called  # another brand's page
    assert not products_sitemap.called


async def test_brand_pages_respect_limit_and_skip_urls(
    settings: Settings, fake_time: FakeTime, mock: respx.MockRouter
) -> None:
    serve_brands(mock)
    async with PoliteFetcher(settings, sleep=fake_time.sleep, clock=fake_time.clock) as f:
        spider = ProfihairshopSpider(f, brands=("wella",))
        spider.skip_urls = frozenset({spider.page_key(f"{BASE}/x/a-1")})
        assert [u async for u in spider.discover(limit=1)] == [f"{BASE}/par/noname-2"]
        assert spider.skipped_seen == 1


async def test_without_a_filter_the_sitemap_adds_what_brand_pages_lack(
    settings: Settings, fake_time: FakeTime, mock: respx.MockRouter
) -> None:
    serve_brands(mock)
    mock.get(f"{BASE}/sitemap-index.xml").mock(
        return_value=httpx.Response(200, text=index(f"{BASE}/products-sitemap.xml"))
    )
    mock.get(f"{BASE}/products-sitemap.xml").mock(
        return_value=httpx.Response(200, text=urlset(f"{BASE}/old/a-1", f"{BASE}/par/only-here"))
    )
    async with PoliteFetcher(settings, sleep=fake_time.sleep, clock=fake_time.clock) as f:
        urls = [u async for u in ProfihairshopSpider(f).discover()]
    assert urls == [
        f"{BASE}/par/a-1",
        f"{BASE}/par/noname-2",
        f"{BASE}/par/a-3",
        f"{BASE}/par/orly-4",
        f"{BASE}/par/only-here",  # /old/a-1 is the same product as /par/a-1
    ]


async def test_unreadable_brand_sitemap_falls_back_to_the_products_sitemap(
    settings: Settings, fake_time: FakeTime, mock: respx.MockRouter
) -> None:
    mock.get(f"{BASE}/robots.txt").mock(return_value=httpx.Response(200, text=ROBOTS))
    mock.get(f"{BASE}/brands-sitemap.xml").mock(return_value=httpx.Response(404))
    mock.get(f"{BASE}/sitemap-index.xml").mock(
        return_value=httpx.Response(200, text=index(f"{BASE}/products-sitemap.xml"))
    )
    mock.get(f"{BASE}/products-sitemap.xml").mock(
        return_value=httpx.Response(200, text=urlset(DYE))
    )
    async with PoliteFetcher(settings, sleep=fake_time.sleep, clock=fake_time.clock) as f:
        assert [u async for u in ProfihairshopSpider(f).discover()] == [DYE]
