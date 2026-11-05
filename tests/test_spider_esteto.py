from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
import respx
from conftest import FakeTime
from selectolax.lexbor import LexborHTMLParser

from beautycrawler.config import Settings
from beautycrawler.crawler.fetcher import PoliteFetcher
from beautycrawler.crawler.runner import load_spiders
from beautycrawler.crawler.spiders.esteto import EstetoSpider

BASE = "https://www.esteto.ro"
FIXTURES = Path(__file__).parent / "fixtures" / "esteto"
OIL = f"{BASE}/produse-828300-short-life-ulei-pur-de-susan-maturat-lakshmi-500-ml"
SERUM = f"{BASE}/produse-828594-ser-fortifiant-pentru-par-cu-rozmarin-bioearth-50-ml"
SHAMPOO = f"{BASE}/produse-828569-sampon-delicat-bioearth-250-ml"
PERFUME = f"{BASE}/produse-900001-apa-de-parfum-50-ml"


def load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def page(*hrefs: str) -> str:
    """A synthetic listing page: only its links matter to discovery."""
    links = "".join(f'<a href="{h}">x</a>' for h in hrefs)
    return f"<html><body>{links}</body></html>"


@pytest.fixture
def spider() -> EstetoSpider:
    return EstetoSpider.__new__(EstetoSpider)  # pure methods need no fetcher


def test_registered() -> None:
    assert load_spiders()["esteto"] is EstetoSpider


def test_parse_product(spider: EstetoSpider) -> None:
    [offer] = spider.parse_product(load("sesame_oil.html"), OIL)
    assert offer.retailer == "esteto"
    assert offer.url == OIL
    assert offer.title == "SHORT LIFE - Ulei Pur de Susan Maturat - Lakshmi, 500 ml"
    assert offer.brand == "Lakshmi"
    assert (offer.price_bani, offer.old_price_bani, offer.currency) == (15800, None, "RON")
    assert offer.in_stock is True
    assert offer.ean is None  # Esteto often has no GTIN
    assert offer.image_url is not None
    assert offer.image_url.startswith(f"{BASE}/static/images/produse/828300/")


def test_tracked_categories_are_linked_from_the_home_page(spider: EstetoSpider) -> None:
    hrefs = {a.attributes.get("href") for a in LexborHTMLParser(load("home_links.html")).css("a")}
    assert set(spider.categories) <= hrefs


def test_home_page_product_links_are_product_urls(spider: EstetoSpider) -> None:
    hrefs = [
        f"{BASE}{a.attributes.get('href')}"
        for a in LexborHTMLParser(load("home_links.html")).css("a")
    ]
    products = [h for h in hrefs if spider.is_product_url(h)]
    assert len(products) == 44  # every /produse-<id>-… link on the page
    assert all("/produse-8" in p for p in products)
    assert not spider.is_product_url(f"{BASE}/produse-cosmetice")
    assert not spider.is_product_url(f"{BASE}/produse-naturiste")


@pytest.mark.parametrize(
    ("url", "listing"),
    [
        (f"{BASE}/produse-cosmetice", f"{BASE}/produse-cosmetice"),
        (f"{BASE}/produse-cosmetice/", f"{BASE}/produse-cosmetice"),
        (f"{BASE}/produse-cosmetice#top", f"{BASE}/produse-cosmetice"),
        (f"{BASE}/produse-cosmetice/ingrijire-par", f"{BASE}/produse-cosmetice/ingrijire-par"),
        (f"{BASE}/produse-cosmetice?page=2", f"{BASE}/produse-cosmetice?page=2"),
        (f"{BASE}/parfumuri?p=3", f"{BASE}/parfumuri?p=3"),
        (f"{BASE}/produse-cosmetice?sort=pret", None),  # sorting: never crawled
        (f"{BASE}/produse-cosmetice?page=2&brand=x", None),  # filters: never crawled
        (f"{BASE}/produse-cosmetice?page=abc", None),
        (f"{BASE}/produse-cosmeticex", None),
        (f"{BASE}/carti", None),  # not a tracked category
        (f"{BASE}/", None),
        ("https://esteto.ro/produse-cosmetice", None),
        ("mailto:contact@esteto.ro", None),
    ],
)
def test_listing_urls(spider: EstetoSpider, url: str, listing: str | None) -> None:
    assert spider.listing_url(url) == listing


class Site:
    """A fake esteto.ro serving `pages` by exact URL (anything else is a 404) and
    recording every requested URL, query included."""

    def __init__(self, mock: respx.MockRouter, pages: dict[str, str], robots: str) -> None:
        self.pages = {f"{BASE}/robots.txt": robots, **pages}
        self.requested: list[str] = []
        mock.route(host="www.esteto.ro").mock(side_effect=self.respond)

    def respond(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if not url.endswith("/robots.txt"):
            self.requested.append(url.removeprefix(BASE))
        text = self.pages.get(url)
        return httpx.Response(404) if text is None else httpx.Response(200, text=text)


@pytest.fixture
def mock() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        yield router


@pytest.fixture
async def live_spider(settings: Settings, fake_time: FakeTime) -> AsyncIterator[EstetoSpider]:
    async with PoliteFetcher(settings, sleep=fake_time.sleep, clock=fake_time.clock) as f:
        yield EstetoSpider(f)


ROBOTS = "User-agent: *\nDisallow: /cos\n"


async def test_discover_walks_category_listings_and_pagination(
    mock: respx.MockRouter, live_spider: EstetoSpider
) -> None:
    site = Site(
        mock,
        {
            f"{BASE}/produse-cosmetice": page(
                "/",
                "/carti",  # another department: not followed
                OIL.removeprefix(BASE),
                f"{SERUM}#reviews",
                "/produse-cosmetice/ingrijire-par",
                "/produse-cosmetice?page=2",
                "/produse-cosmetice?sort=pret",  # sorting: not followed
            ),
            f"{BASE}/parfumuri": page(PERFUME),
            f"{BASE}/produse-cosmetice/ingrijire-par": page(SHAMPOO),
            f"{BASE}/produse-cosmetice?page=2": page(
                SERUM, SHAMPOO, "/produse-cosmetice", "/produse-cosmetice?page=3"
            ),
            f"{BASE}/produse-cosmetice?page=3": page(f"{BASE}/produse-900002-ruj-mat"),
        },
        ROBOTS,
    )

    urls = [u async for u in live_spider.discover()]

    assert urls == [OIL, SERUM, PERFUME, SHAMPOO, f"{BASE}/produse-900002-ruj-mat"]
    # Breadth-first, each listing page once, nothing outside the tracked categories.
    assert site.requested == [
        "/produse-cosmetice",
        "/parfumuri",
        "/produse-cosmetice/ingrijire-par",
        "/produse-cosmetice?page=2",
        "/produse-cosmetice?page=3",
    ]


async def test_discover_respects_limit(mock: respx.MockRouter, live_spider: EstetoSpider) -> None:
    site = Site(
        mock,
        {f"{BASE}/produse-cosmetice": page(OIL, SERUM, "/produse-cosmetice?page=2")},
        ROBOTS,
    )

    assert [u async for u in live_spider.discover(limit=2)] == [OIL, SERUM]
    assert site.requested == ["/produse-cosmetice"]


async def test_discover_skips_disallowed_and_failing_listings(
    mock: respx.MockRouter, live_spider: EstetoSpider
) -> None:
    site = Site(
        mock,
        {
            f"{BASE}/produse-cosmetice": page(OIL, "/produse-cosmetice/machiaj"),
            f"{BASE}/produse-cosmetice/machiaj": page(SERUM),
        },
        "User-agent: *\nDisallow: /produse-cosmetice/machiaj\n",
    )

    assert [u async for u in live_spider.discover()] == [OIL]
    assert site.requested == ["/produse-cosmetice", "/parfumuri"]  # /parfumuri is a 404


async def test_listing_page_cap(
    mock: respx.MockRouter, live_spider: EstetoSpider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(EstetoSpider, "max_listing_pages", 1)
    site = Site(mock, {f"{BASE}/produse-cosmetice": page(OIL)}, ROBOTS)

    assert [u async for u in live_spider.discover()] == [OIL]
    assert site.requested == ["/produse-cosmetice"]


async def test_crawl(mock: respx.MockRouter, live_spider: EstetoSpider) -> None:
    Site(
        mock,
        {
            f"{BASE}/produse-cosmetice": page(OIL),
            f"{BASE}/parfumuri": page(),
            OIL: load("sesame_oil.html"),
        },
        ROBOTS,
    )

    offers = [o async for o in live_spider.crawl()]

    assert [(o.url, o.price_bani, o.brand) for o in offers] == [(OIL, 15800, "Lakshmi")]
