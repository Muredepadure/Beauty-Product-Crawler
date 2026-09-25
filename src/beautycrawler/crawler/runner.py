"""Run spiders and store their offers (P1.3 write path)."""

import importlib
import logging
import pkgutil
from collections import Counter
from dataclasses import dataclass, field
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

    def line(self) -> str:
        if self.failed:
            return f"{self.retailer}: FAILED: {self.failed}"
        o = self.outcomes
        return (
            f"{self.retailer}: {self.stats.pages_fetched} pages, {self.stats.offers} offers "
            f"({o['created']} new, {o['changed']} changed, {o['unchanged']} unchanged, "
            f"{o['stale']} stale), {len(self.stats.errors)} errors"
        )


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
        session.commit()
    return summary


async def run_many(
    slugs: list[str],
    session_factory: sessionmaker[Session],
    fetcher: PoliteFetcher,
    limit: int | None = None,
) -> list[RunSummary]:
    """Run retailers one after another; one failing retailer doesn't stop the others."""
    summaries = []
    for slug in slugs:
        try:
            summaries.append(await run_spider(slug, session_factory, fetcher, limit))
        except Exception as exc:
            log.exception("crawl of %s failed", slug)
            summaries.append(RunSummary(retailer=slug, failed=f"{type(exc).__name__}: {exc}"))
    return summaries
