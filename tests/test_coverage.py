"""Coverage checks: the site against the database, and barcodes shared between shops."""

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import ClassVar

import httpx
import pytest
import respx
from conftest import FakeTime
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from beautycrawler.config import Settings
from beautycrawler.crawler.__main__ import main
from beautycrawler.crawler.coverage import barcode_overlap, site_coverage
from beautycrawler.crawler.fetcher import PoliteFetcher
from beautycrawler.crawler.spider import JsonLdSpider, register
from beautycrawler.db import Base
from beautycrawler.db.models import Offer, Product, Retailer
from beautycrawler.db.session import make_engine, make_session_factory

BASE = "https://coverage.example.ro"


@register
class CoverageSpider(JsonLdSpider):
    slug = "coverage-shop"
    name = "Coverage Shop"
    base_url = BASE
    sitemap_urls: ClassVar[tuple[str, ...]] = ()


@pytest.fixture
def mock() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        items = "".join(f"<url><loc>{BASE}/p/{n}</loc></url>" for n in (1, 2, 3))
        robots = f"User-agent: *\nSitemap: {BASE}/sitemap.xml\n"
        sitemap = f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}</urlset>'
        router.get(f"{BASE}/robots.txt").mock(return_value=httpx.Response(200, text=robots))
        router.get(f"{BASE}/sitemap.xml").mock(return_value=httpx.Response(200, text=sitemap))
        yield router


def offer(retailer: Retailer, url: str, ean: str | None, product: Product | None) -> Offer:
    return Offer(
        retailer=retailer,
        product=product,
        url=url,
        title="x",
        ean=ean,
        price_bani=1_000,
        in_stock=True,
    )


def fetcher_factory(settings: Settings, fake_time: FakeTime) -> Callable[[], PoliteFetcher]:
    return lambda: PoliteFetcher(settings, sleep=fake_time.sleep, clock=fake_time.clock)


async def test_site_coverage(
    mock: respx.MockRouter, session: Session, settings: Settings, fake_time: FakeTime
) -> None:
    shop = Retailer(slug="coverage-shop", name="Coverage Shop", domain="coverage.example.ro")
    other = Retailer(slug="other", name="Other", domain="other.ro")
    session.add_all(
        [
            offer(shop, f"{BASE}/p/1", None, None),
            offer(shop, f"{BASE}/p/gone", None, None),  # stored, no longer on the site
            offer(other, f"{BASE}/p/2", None, None),  # another shop's listing doesn't count
        ]
    )
    session.commit()
    async with fetcher_factory(settings, fake_time)() as f:
        report = await site_coverage(CoverageSpider(f), session)
    assert (report.on_site, report.collected) == (3, 1)
    assert report.missing == [f"{BASE}/p/2", f"{BASE}/p/3"]
    assert report.line() == "coverage-shop: 3 on the site, 1 collected (33%), 2 missing"


def test_barcode_overlap(session: Session) -> None:
    a = Retailer(slug="a", name="A", domain="a.ro")
    b = Retailer(slug="b", name="B", domain="b.ro")
    one = Product(name="one", normalized_name="one")
    two = Product(name="two", normalized_name="two")
    session.add_all(
        [
            offer(a, "https://a.ro/1", "111", one),  # linked
            offer(b, "https://b.ro/1", "111", one),
            offer(a, "https://a.ro/2", "222", one),  # same barcode, different products
            offer(b, "https://b.ro/2", "222", two),
            offer(a, "https://a.ro/3", "333", None),  # same barcode, not linked yet
            offer(b, "https://b.ro/3", "333", None),
            offer(a, "https://a.ro/4", "444", one),  # only at one shop
            offer(a, "https://a.ro/5", None, one),  # no barcode
            offer(b, "https://b.ro/5", None, one),
        ]
    )
    session.commit()
    report = barcode_overlap(session, "a", "b")
    assert (report.shared, report.linked, report.unlinked) == (3, 1, 2)
    assert report.line() == "a + b: 3 shared barcodes, 1 linked to one product, 2 not linked"


def test_coverage_command(
    mock: respx.MockRouter,
    tmp_path: Path,
    settings: Settings,
    fake_time: FakeTime,
    capsys: pytest.CaptureFixture[str],
) -> None:
    url = f"sqlite:///{tmp_path / 'c.db'}"
    engine: Engine = make_engine(url)
    Base.metadata.create_all(engine)
    with make_session_factory(engine)() as s:
        shop = Retailer(slug="coverage-shop", name="Coverage Shop", domain="coverage.example.ro")
        s.add(offer(shop, f"{BASE}/p/1", None, None))
        s.commit()
    engine.dispose()
    argv = ["coverage", "--retailer", "coverage-shop", "--database-url", url, "--show-missing", "1"]
    assert main(argv, fetcher_factory(settings, fake_time)) == 0
    out = capsys.readouterr().out
    assert "3 on the site, 1 collected (33%), 2 missing" in out
    assert f"missing: {BASE}/p/2" in out and f"{BASE}/p/3" not in out
    assert main(["coverage", "--retailer", "nope", "--database-url", url]) == 2
