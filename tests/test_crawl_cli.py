import json
import logging
from collections.abc import AsyncIterator, Callable, Iterator
from datetime import UTC, datetime, timedelta
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
from beautycrawler.logs import JsonFormatter, configure_logging

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


# --- P6.1: crawl job report, inactive retailers, structured logs ---------------------


def test_summary_json_report(
    mock: respx.MockRouter,
    db: tuple[str, Engine],
    settings: Settings,
    fake_time: FakeTime,
    tmp_path: Path,
) -> None:
    url, _ = db
    report_path = tmp_path / "report.json"
    argv = [
        "run",
        "--retailer",
        "clitest-broken",
        "--retailer",
        "clitest",
        "--database-url",
        url,
        "--summary-json",
        str(report_path),
    ]
    assert main(argv, fetcher_factory(settings, fake_time)) == 1
    report = json.loads(report_path.read_text("utf-8"))
    assert report["ok"] is False
    assert report["totals"] == {
        "retailers": 2,
        "succeeded": 1,
        "failed": 1,
        "skipped": 0,
        "pages_fetched": 2,
        "offers": 2,
        "errors": 0,
    }
    broken, ok = report["retailers"]
    assert (broken["retailer"], broken["status"]) == ("clitest-broken", "failed")
    assert broken["failed"] == "RuntimeError: site layout changed"
    assert (ok["retailer"], ok["status"], ok["failed"]) == ("clitest", "ok", None)
    assert ok["outcomes"] == {"created": 1, "changed": 0, "unchanged": 1, "stale": 0}
    assert ok["duration_seconds"] >= 0
    started = datetime.fromisoformat(report["started_at"])
    assert started <= datetime.fromisoformat(report["finished_at"])


def test_inactive_retailer_is_skipped(
    mock: respx.MockRouter,
    db: tuple[str, Engine],
    settings: Settings,
    fake_time: FakeTime,
    capsys: pytest.CaptureFixture[str],
) -> None:
    url, engine = db
    with Session(engine) as s:
        s.add(
            Retailer(slug="clitest", name="Blocked", domain="clitest.example.ro", is_active=False)
        )
        s.commit()
    argv = ["run", "--retailer", "clitest", "--database-url", url]
    assert main(argv, fetcher_factory(settings, fake_time)) == 0
    assert "clitest: skipped: retailer is marked inactive" in capsys.readouterr().out
    assert count(engine, Offer) == 0
    assert not mock.calls  # not a single request to the site

    assert main([*argv, "--include-inactive"], fetcher_factory(settings, fake_time)) == 0
    assert count(engine, Offer) == 1


def test_match_after_crawl(
    mock: respx.MockRouter,
    db: tuple[str, Engine],
    settings: Settings,
    fake_time: FakeTime,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    url, engine = db
    report_path = tmp_path / "r.json"
    argv = ["run", "--retailer", "clitest", "--database-url", url, "--match"]
    argv += ["--summary-json", str(report_path)]
    assert main(argv, fetcher_factory(settings, fake_time)) == 0
    assert "matching: new_product 1" in capsys.readouterr().out
    assert json.loads(report_path.read_text("utf-8"))["matching"] == {"new_product": 1}
    with Session(engine) as s:
        assert s.scalars(select(Offer)).one().product_id is not None


def test_json_logs(
    mock: respx.MockRouter,
    db: tuple[str, Engine],
    settings: Settings,
    fake_time: FakeTime,
    capsys: pytest.CaptureFixture[str],
) -> None:
    url, _ = db
    argv = ["-v", "--log-format", "json", "run", "--retailer", "clitest-broken"]
    argv += ["--retailer", "clitest", "--database-url", url]
    try:
        main(argv, fetcher_factory(settings, fake_time))
    finally:
        configure_logging()  # back to quiet text logging for later tests
    lines = [json.loads(line) for line in capsys.readouterr().err.splitlines() if line]
    events = {e.get("event"): e for e in lines if "event" in e}
    finished = events["crawl_finished"]
    assert (finished["retailer"], finished["level"], finished["pages_fetched"]) == (
        "clitest",
        "INFO",
        2,
    )
    failed = events["crawl_failed"]
    assert (failed["retailer"], failed["level"]) == ("clitest-broken", "ERROR")
    assert "RuntimeError: site layout changed" in failed["exception"]


def test_json_formatter() -> None:
    record = logging.LogRecord("beautycrawler.x", logging.WARNING, "f.py", 1, "hi %s", ("ș",), None)
    record.retailer = "notino"
    entry = json.loads(JsonFormatter().format(record))
    assert entry["message"] == "hi ș"
    assert (entry["level"], entry["logger"], entry["retailer"]) == (
        "WARNING",
        "beautycrawler.x",
        "notino",
    )
    assert entry["ts"].endswith("+00:00")
    assert "args" not in entry and "exception" not in entry


async def test_run_many_measures_each_retailer(
    mock: respx.MockRouter, db: tuple[str, Engine], settings: Settings, fake_time: FakeTime
) -> None:
    _, engine = db
    ticks = iter([10.0, 12.5, 20.0, 21.0])
    async with PoliteFetcher(settings, sleep=fake_time.sleep, clock=fake_time.clock) as f:
        report = await runner.run_many(
            ["clitest", "clitest-broken"],
            make_session_factory(engine),
            f,
            clock=lambda: next(ticks),
        )
    assert [s.duration_seconds for s in report.summaries] == [2.5, 1.0]
    assert [s.status for s in report.summaries] == ["ok", "failed"]
    assert report.ok is False


# --- P6.2: per-retailer schedule ------------------------------------------------------


def _retailer(engine: Engine) -> Retailer:
    with Session(engine) as s:
        return s.scalars(select(Retailer).where(Retailer.slug == "clitest")).one()


def test_successful_crawl_stamps_last_crawled_at(
    mock: respx.MockRouter, db: tuple[str, Engine], settings: Settings, fake_time: FakeTime
) -> None:
    url, engine = db
    before = datetime.now(UTC)
    main(
        ["run", "--retailer", "clitest", "--database-url", url],
        fetcher_factory(settings, fake_time),
    )
    stamped = _retailer(engine).last_crawled_at
    assert stamped is not None
    assert stamped.replace(tzinfo=UTC) >= before


def test_failed_crawl_is_not_stamped(
    mock: respx.MockRouter, db: tuple[str, Engine], settings: Settings, fake_time: FakeTime
) -> None:
    url, engine = db
    main(
        ["run", "--retailer", "clitest-broken", "--database-url", url],
        fetcher_factory(settings, fake_time),
    )
    with Session(engine) as s:
        broken = s.scalars(select(Retailer).where(Retailer.slug == "clitest-broken")).one()
        assert broken.last_crawled_at is None  # so the next --due run retries it


@pytest.mark.parametrize(
    ("hours_ago", "interval", "crawled"),
    [(None, 24, True), (1, 24, False), (25, 24, True), (7, 6, True), (5, 6, False)],
)
def test_due_only(
    mock: respx.MockRouter,
    db: tuple[str, Engine],
    settings: Settings,
    fake_time: FakeTime,
    capsys: pytest.CaptureFixture[str],
    hours_ago: int | None,
    interval: int,
    crawled: bool,
) -> None:
    url, engine = db
    last = datetime.now(UTC) - timedelta(hours=hours_ago) if hours_ago is not None else None
    with Session(engine) as s:
        s.add(
            Retailer(
                slug="clitest",
                name="Shop",
                domain="clitest.example.ro",
                crawl_interval_hours=interval,
                last_crawled_at=last,
            )
        )
        s.commit()
    argv = ["run", "--retailer", "clitest", "--due", "--database-url", url]
    assert main(argv, fetcher_factory(settings, fake_time)) == 0
    out = capsys.readouterr().out
    assert (count(engine, Offer) == 1) is crawled
    assert ("skipped: not due until" in out) is not crawled


def test_due_for_retailer_never_seen(
    mock: respx.MockRouter, db: tuple[str, Engine], settings: Settings, fake_time: FakeTime
) -> None:
    url, engine = db  # no Retailer row yet: never crawled, so due
    argv = ["run", "--retailer", "clitest", "--due", "--database-url", url]
    assert main(argv, fetcher_factory(settings, fake_time)) == 0
    assert count(engine, Offer) == 1


def test_schedule_show_and_set(db: tuple[str, Engine], capsys: pytest.CaptureFixture[str]) -> None:
    url, engine = db
    assert main(["schedule", "--database-url", url]) == 0
    assert "No retailers in the database" in capsys.readouterr().out
    with Session(engine) as s:
        s.add(Retailer(slug="clitest", name="Shop", domain="clitest.example.ro"))
        s.add(
            Retailer(
                slug="other",
                name="Other",
                domain="other.ro",
                is_active=False,
                last_crawled_at=datetime(2026, 9, 25, 10, 0, tzinfo=UTC),
            )
        )
        s.commit()
    assert (
        main(["schedule", "--retailer", "clitest", "--every-hours", "6", "--database-url", url])
        == 0
    )
    out = capsys.readouterr().out
    assert "clitest         every   6 h  last never             next now" in out
    assert (
        "other           every  24 h  last 2026-09-25 10:00  next 2026-09-26 10:00  (inactive)"
        in out
    )
    assert _retailer(engine).crawl_interval_hours == 6


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--retailer", "clitest"], "go together"),
        (["--every-hours", "3"], "go together"),
        (["--retailer", "clitest", "--every-hours", "0"], ">= 1"),
        (["--retailer", "nope", "--every-hours", "3"], "Unknown retailer: nope"),
    ],
)
def test_schedule_errors(
    db: tuple[str, Engine], capsys: pytest.CaptureFixture[str], args: list[str], message: str
) -> None:
    url, _ = db
    assert main(["schedule", *args, "--database-url", url]) == 2
    assert message in capsys.readouterr().err
