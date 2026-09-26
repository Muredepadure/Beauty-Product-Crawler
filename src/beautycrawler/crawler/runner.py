"""Run spiders and store their offers (P1.3 write path).

`run_many` is the crawl job: retailers run one after another, each isolated (a failing
site is recorded and the next one runs), each emitting a structured `crawl_finished` /
`crawl_failed` log event; `RunReport` sums the run up for the CLI and schedulers.
Retailers marked inactive in the database (e.g. blocked, see CLAUDE.md) are skipped.

Scheduling (P6.2): a successful crawl stamps `Retailer.last_crawled_at`; with `due_only`
a retailer is crawled only once its `crawl_interval_hours` have passed, so an hourly cron
job running `crawl run --all --due` gives every retailer its own frequency.
"""

import importlib
import logging
import pkgutil
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from beautycrawler.crawler import spiders as spiders_pkg
from beautycrawler.crawler.fetcher import PoliteFetcher
from beautycrawler.crawler.spider import CrawlStats, Spider, get_spider, registered_spiders
from beautycrawler.db.models import Retailer
from beautycrawler.db.repository import upsert_offer

log = logging.getLogger(__name__)

COMMIT_EVERY = 50


@dataclass(slots=True)
class RunSummary:
    retailer: str
    stats: CrawlStats = field(default_factory=CrawlStats)
    outcomes: Counter[str] = field(default_factory=Counter)
    failed: str | None = None  # set when the whole run aborted
    skipped: str | None = None  # set when the retailer was not crawled at all
    duration_seconds: float = 0.0

    def line(self) -> str:
        if self.skipped:
            return f"{self.retailer}: skipped: {self.skipped}"
        if self.failed:
            return f"{self.retailer}: FAILED: {self.failed}"
        o = self.outcomes
        return (
            f"{self.retailer}: {self.stats.pages_fetched} pages, {self.stats.offers} offers "
            f"({o['created']} new, {o['changed']} changed, {o['unchanged']} unchanged, "
            f"{o['stale']} stale), {len(self.stats.errors)} errors"
        )

    @property
    def status(self) -> str:
        return "skipped" if self.skipped else "failed" if self.failed else "ok"

    def to_dict(self) -> dict[str, Any]:
        return {
            "retailer": self.retailer,
            "status": self.status,
            "failed": self.failed,
            "skipped": self.skipped,
            "duration_seconds": round(self.duration_seconds, 3),
            "pages_fetched": self.stats.pages_fetched,
            "offers": self.stats.offers,
            "pages_without_offers": self.stats.pages_without_offers,
            "outcomes": {k: self.outcomes[k] for k in ("created", "changed", "unchanged", "stale")},
            "errors": list(self.stats.errors),
        }


@dataclass(slots=True)
class RunReport:
    """A whole crawl job: when it ran and each retailer's summary."""

    started_at: datetime
    finished_at: datetime
    summaries: list[RunSummary]

    @property
    def ok(self) -> bool:
        return not any(s.failed for s in self.summaries)

    def to_dict(self) -> dict[str, Any]:
        crawled = [s for s in self.summaries if s.status == "ok"]
        return {
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "duration_seconds": round((self.finished_at - self.started_at).total_seconds(), 3),
            "ok": self.ok,
            "totals": {
                "retailers": len(self.summaries),
                "succeeded": len(crawled),
                "failed": sum(1 for s in self.summaries if s.failed),
                "skipped": sum(1 for s in self.summaries if s.skipped),
                "pages_fetched": sum(s.stats.pages_fetched for s in crawled),
                "offers": sum(s.stats.offers for s in crawled),
                "errors": sum(len(s.stats.errors) for s in crawled),
            },
            "retailers": [s.to_dict() for s in self.summaries],
        }


def load_spiders() -> dict[str, type[Spider]]:
    """Import every module in `crawler.spiders` so their @register decorators run."""
    for module in pkgutil.iter_modules(spiders_pkg.__path__):
        importlib.import_module(f"{spiders_pkg.__name__}.{module.name}")
    return registered_spiders()


def get_or_create_retailer(session: Session, spider_cls: type[Spider]) -> Retailer:
    retailer = session.scalars(
        select(Retailer).where(Retailer.slug == spider_cls.slug)
    ).one_or_none()
    if retailer is None:
        domain = urlsplit(spider_cls.base_url).netloc.lower().removeprefix("www.")
        retailer = Retailer(slug=spider_cls.slug, name=spider_cls.name, domain=domain)
        session.add(retailer)
        session.flush()
    return retailer


async def run_spider(
    slug: str,
    session_factory: sessionmaker[Session],
    fetcher: PoliteFetcher,
    limit: int | None = None,
) -> RunSummary:
    """Crawl one retailer and upsert every offer. Commits in batches."""
    spider_cls = get_spider(slug)
    summary = RunSummary(retailer=slug)
    spider = spider_cls(fetcher)
    with session_factory() as session:
        retailer = get_or_create_retailer(session, spider_cls)
        session.commit()
        pending = 0
        async for offer in spider.crawl(limit=limit, stats=summary.stats):
            if offer.retailer != slug:
                summary.stats.errors.append(f"{offer.url}: offer for {offer.retailer!r}")
                continue
            result = upsert_offer(session, retailer, offer.to_snapshot(), offer.scraped_at)
            summary.outcomes[result.outcome.value] += 1
            pending += 1
            if pending >= COMMIT_EVERY:
                session.commit()
                pending = 0
        retailer.last_crawled_at = datetime.now(UTC)
        session.commit()
    return summary


def inactive_retailers(session_factory: sessionmaker[Session], slugs: list[str]) -> set[str]:
    """Slugs whose retailer row exists and is marked inactive."""
    with session_factory() as session:
        return set(
            session.scalars(
                select(Retailer.slug).where(Retailer.slug.in_(slugs), Retailer.is_active.is_(False))
            )
        )


def _as_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def next_due(retailer: Retailer) -> datetime | None:
    """When the retailer is next due for a crawl (None: never crawled, due now)."""
    if retailer.last_crawled_at is None:
        return None
    return _as_utc(retailer.last_crawled_at) + timedelta(hours=retailer.crawl_interval_hours)


def not_due_retailers(
    session_factory: sessionmaker[Session], slugs: list[str], now: datetime
) -> dict[str, datetime]:
    """slug -> next due time, for retailers crawled more recently than their interval.
    Retailers without a row yet have never been crawled, so they are due."""
    with session_factory() as session:
        retailers = session.scalars(select(Retailer).where(Retailer.slug.in_(slugs)))
        return {r.slug: due for r in retailers if (due := next_due(r)) is not None and due > now}


async def run_many(
    slugs: list[str],
    session_factory: sessionmaker[Session],
    fetcher: PoliteFetcher,
    limit: int | None = None,
    *,
    include_inactive: bool = False,
    due_only: bool = False,
    clock: Callable[[], float] = time.monotonic,
) -> RunReport:
    """Run retailers one after another; one failing retailer doesn't stop the others."""
    started_at = datetime.now(UTC)
    inactive = set() if include_inactive else inactive_retailers(session_factory, slugs)
    not_due = not_due_retailers(session_factory, slugs, started_at) if due_only else {}
    summaries = []
    for slug in slugs:
        reason = None
        if slug in inactive:
            reason = "retailer is marked inactive"
        elif slug in not_due:
            reason = f"not due until {not_due[slug].isoformat(timespec='minutes')}"
        if reason is not None:
            log.info(
                "%s: skipped (%s)",
                slug,
                reason,
                extra={"event": "crawl_skipped", "retailer": slug, "reason": reason},
            )
            summaries.append(RunSummary(retailer=slug, skipped=reason))
            continue
        start = clock()
        try:
            summary = await run_spider(slug, session_factory, fetcher, limit)
        except Exception as exc:
            summary = RunSummary(retailer=slug, failed=f"{type(exc).__name__}: {exc}")
            summary.duration_seconds = clock() - start
            log.exception(
                "crawl of %s failed",
                slug,
                extra={"event": "crawl_failed", **summary.to_dict()},
            )
        else:
            summary.duration_seconds = clock() - start
            log.info(
                "%s: crawl finished", slug, extra={"event": "crawl_finished", **summary.to_dict()}
            )
        summaries.append(summary)
    return RunReport(started_at, datetime.now(UTC), summaries)
