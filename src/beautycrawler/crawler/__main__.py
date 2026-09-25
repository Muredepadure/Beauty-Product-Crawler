"""Crawl CLI.

    python -m beautycrawler.crawler list
    python -m beautycrawler.crawler run --retailer notino [--limit N]
    python -m beautycrawler.crawler run --all [--limit N]

The database schema must exist (`alembic upgrade head`).
"""

import argparse
import asyncio
import logging
import sys
from collections.abc import Callable

from beautycrawler.config import get_settings
from beautycrawler.crawler.fetcher import PoliteFetcher
from beautycrawler.crawler.runner import RunSummary, load_spiders, run_many
from beautycrawler.db.session import make_engine, make_session_factory

FetcherFactory = Callable[[], PoliteFetcher]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m beautycrawler.crawler")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="list registered spiders")
    run = sub.add_parser("run", help="crawl retailers and store offers")
    which = run.add_mutually_exclusive_group(required=True)
    which.add_argument("--retailer", action="append", metavar="SLUG", help="repeatable")
    which.add_argument("--all", action="store_true", help="every registered spider")
    run.add_argument("--limit", type=int, help="max product pages per retailer")
    run.add_argument("--database-url", help="override DATABASE_URL")
    return parser


async def _run(
    slugs: list[str], database_url: str | None, limit: int | None, fetcher_factory: FetcherFactory
) -> list[RunSummary]:
    engine = make_engine(database_url)
    try:
        async with fetcher_factory() as fetcher:
            return await run_many(slugs, make_session_factory(engine), fetcher, limit)
    finally:
        engine.dispose()


def main(argv: list[str] | None = None, fetcher_factory: FetcherFactory | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    spiders = load_spiders()

    if args.command == "list":
        if not spiders:
            print("No spiders registered yet.")
        for slug, cls in sorted(spiders.items()):
            print(f"{slug:15} {cls.name:25} {cls.base_url}")
        return 0

    if args.limit is not None and args.limit < 1:
        print("--limit must be >= 1", file=sys.stderr)
        return 2
    slugs = sorted(spiders) if args.all else list(dict.fromkeys(args.retailer))
    unknown = [s for s in slugs if s not in spiders]
    if unknown:
        known = ", ".join(sorted(spiders)) or "none"
        print(f"Unknown retailer(s): {', '.join(unknown)} (registered: {known})", file=sys.stderr)
        return 2
    if not slugs:
        print("No spiders registered yet; nothing to crawl.")
        return 0

    factory = fetcher_factory or (lambda: PoliteFetcher(get_settings()))
    summaries = asyncio.run(_run(slugs, args.database_url, args.limit, factory))
    for summary in summaries:
        print(summary.line())
    return 1 if any(s.failed for s in summaries) else 0


if __name__ == "__main__":
    raise SystemExit(main())
