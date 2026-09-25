from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path

import httpx
import pytest
import respx
from conftest import FakeTime
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from beautycrawler.config import Settings
from beautycrawler.crawler import runner
from beautycrawler.crawler.__main__ import main
from beautycrawler.crawler.fetcher import PoliteFetcher
from beautycrawler.crawler.spider import JsonLdSpider, register
from beautycrawler.db import Base, Offer, PriceHistory, Retailer
from beautycrawler.db.session import make_engine, make_session_factory

BASE = "https://clitest.example.ro"
BROKEN = "https://broken.example.ro"
HTML = (Path(__file__).parent / "fixtures" / "jsonld" / "single_offer.html").read_text("utf-8")


@register
class CliTestSpider(JsonLdSpider):
    slug = "clitest"
    name = "CLI Test Shop"
    base_url = BASE

    def is_product_url(self, url: str) -> bool:
        return "/p/" in url


@register
class BrokenSpider(JsonLdSpider):
    slug = "clitest-broken"
    name = "Broken"
    base_url = BROKEN

    async def discover(self, limit: int | None = None) -> AsyncIterator[str]:
        raise RuntimeError("site layout changed")
        yield  # pragma: no cover


def urlset(*urls: str) -> str:
    items = "".join(f"<url><loc>{u}</loc></url>" for u in urls)
    return f"<urlset>{items}</urlset>"


@pytest.fixture
def mock() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        router.get(f"{BASE}/robots.txt").mock(
            return_value=httpx.Response(200, text=f"User-agent: *\nSitemap: {BASE}/sm.xml\n")
        )
        router.get(f"{BASE}/sm.xml").mock(
            return_value=httpx.Response(200, text=urlset(f"{BASE}/p/1", f"{BASE}/p/2"))
        )
        router.get(url__regex=rf"{BASE}/p/\d").mock(return_value=httpx.Response(200, text=HTML))
        yield router


@pytest.fixture
def db(tmp_path: Path) -> Iterator[tuple[str, Engine]]:
    url = f"sqlite:///{tmp_path / 'crawl.db'}"
    engine = make_engine(url)
    Base.metadata.create_all(engine)
    yield url, engine
    engine.dispose()


def fetcher_factory(settings: Settings, fake_time: FakeTime) -> Callable[[], PoliteFetcher]:
    return lambda: PoliteFetcher(settings, sleep=fake_time.sleep, clock=fake_time.clock)


def count(engine: Engine, model: type) -> int:
    with Session(engine) as s:
        return s.scalar(select(func.count()).select_from(model)) or 0


def test_run_retailer_writes_offers(
    mock: respx.MockRouter,
    db: tuple[str, Engine],
    settings: Settings,
    fake_time: FakeTime,
    capsys: pytest.CaptureFixture[str],
) -> None:
    url, engine = db
    factory = fetcher_factory(settings, fake_time)
    assert main(["run", "--retailer", "clitest", "--database-url", url], factory) == 0
    out = capsys.readouterr().out
    # Both product pages resolve to the same canonical offer URL in the fixture.
    assert "clitest: 2 pages, 2 offers (1 new, 0 changed, 1 unchanged, 0 stale), 0 errors" in out

    with Session(engine) as s:
        retailer = s.scalars(select(Retailer).where(Retailer.slug == "clitest")).one()
        assert (retailer.name, retailer.domain) == ("CLI Test Shop", "clitest.example.ro")
        offer = s.scalars(select(Offer)).one()
        assert (offer.price_bani, offer.ean) == (8999, "3337875598996")
    assert count(engine, PriceHistory) == 1

    # Second run: nothing changed, so no new history.
    assert main(["run", "--retailer", "clitest", "--database-url", url], factory) == 0
    assert "0 new, 0 changed, 2 unchanged" in capsys.readouterr().out
    assert count(engine, PriceHistory) == 1


def test_limit(
    mock: respx.MockRouter,
    db: tuple[str, Engine],
    settings: Settings,
    fake_time: FakeTime,
    capsys: pytest.CaptureFixture[str],
) -> None:
    url, _ = db
    argv = ["run", "--retailer", "clitest", "--limit", "1", "--database-url", url]
    assert main(argv, fetcher_factory(settings, fake_time)) == 0
    assert "clitest: 1 pages, 1 offers" in capsys.readouterr().out


def test_uses_existing_seeded_retailer(
    mock: respx.MockRouter, db: tuple[str, Engine], settings: Settings, fake_time: FakeTime
) -> None:
    url, engine = db
    with Session(engine) as s:
        s.add(Retailer(slug="clitest", name="Seeded name", domain="clitest.example.ro"))
        s.commit()
    main(
        ["run", "--retailer", "clitest", "--database-url", url],
        fetcher_factory(settings, fake_time),
    )
    assert count(engine, Retailer) == 1
    with Session(engine) as s:
        assert s.scalars(select(Retailer)).one().name == "Seeded name"


def test_one_failing_retailer_does_not_stop_others(
    mock: respx.MockRouter,
    db: tuple[str, Engine],
    settings: Settings,
    fake_time: FakeTime,
    capsys: pytest.CaptureFixture[str],
) -> None:
    url, engine = db
    argv = ["run", "--retailer", "clitest-broken", "--retailer", "clitest", "--database-url", url]
    assert main(argv, fetcher_factory(settings, fake_time)) == 1  # non-zero: something failed
    out = capsys.readouterr().out
    assert "clitest-broken: FAILED: RuntimeError: site layout changed" in out
    assert "clitest: 2 pages" in out
    assert count(engine, Offer) == 1


def test_unknown_retailer(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["run", "--retailer", "nope"]) == 2
    assert "Unknown retailer(s): nope" in capsys.readouterr().err


def test_invalid_limit(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["run", "--retailer", "clitest", "--limit", "0"]) == 2


def test_retailer_and_all_are_exclusive() -> None:
    with pytest.raises(SystemExit):
        main(["run", "--retailer", "clitest", "--all"])


def test_list(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["list"]) == 0
    assert "clitest" in capsys.readouterr().out


def test_load_spiders_imports_spider_package() -> None:
    spiders = runner.load_spiders()
    assert spiders["clitest"] is CliTestSpider


async def test_run_spider_commits_in_batches(
    monkeypatch: pytest.MonkeyPatch,
    mock: respx.MockRouter,
    db: tuple[str, Engine],
    settings: Settings,
    fake_time: FakeTime,
) -> None:
    monkeypatch.setattr(runner, "COMMIT_EVERY", 1)
    _, engine = db
    async with PoliteFetcher(settings, sleep=fake_time.sleep, clock=fake_time.clock) as f:
        summary = await runner.run_spider("clitest", make_session_factory(engine), f)
    assert summary.failed is None
    assert summary.outcomes["created"] == 1
