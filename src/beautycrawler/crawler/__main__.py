"""Crawl CLI.

    python -m beautycrawler.crawler list
    python -m beautycrawler.crawler run --retailer notino [--limit N]
    python -m beautycrawler.crawler run --all [--limit N]
    python -m beautycrawler.crawler run --all --due      # hourly cron entry point
    python -m beautycrawler.crawler schedule [--retailer SLUG --every-hours N]

Options for `run`: `--due` skips retailers crawled within their interval;
`--match` links new offers to products afterwards;
`--summary-json PATH` writes the run report; `--include-inactive` also crawls retailers
marked inactive in the database. `--log-format json` (before the command) gives one JSON
log object per line. Exit code 1 when any retailer failed.

The database schema must exist (`alembic upgrade head`).
"""

import argparse
import asyncio
import json
import sys
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import select

from beautycrawler.config import get_settings
from beautycrawler.crawler.fetcher import PoliteFetcher
from beautycrawler.crawler.runner import RunReport, load_spiders, next_due, run_many
from beautycrawler.db.models import Retailer
from beautycrawler.db.session import make_engine, make_session_factory
from beautycrawler.logs import configure_logging
from beautycrawler.matching.service import match_unmatched

FetcherFactory = Callable[[], PoliteFetcher]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m beautycrawler.crawler")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--log-format", choices=["text", "json"], default="text")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="list registered spiders")
    run = sub.add_parser("run", help="crawl retailers and store offers")
    which = run.add_mutually_exclusive_group(required=True)
    which.add_argument("--retailer", action="append", metavar="SLUG", help="repeatable")
    which.add_argument("--all", action="store_true", help="every registered spider")
    run.add_argument("--limit", type=int, help="max product pages per retailer")
    run.add_argument("--database-url", help="override DATABASE_URL")
    run.add_argument("--match", action="store_true", help="match new offers to products after")
    run.add_argument("--summary-json", type=Path, metavar="PATH", help="write the run report")
    run.add_argument(
        "--include-inactive", action="store_true", help="also crawl retailers marked inactive"
    )
    run.add_argument(
        "--due", action="store_true", help="only retailers whose crawl interval has passed"
    )

    schedule = sub.add_parser("schedule", help="show or set per-retailer crawl intervals")
    schedule.add_argument("--retailer", metavar="SLUG", help="retailer to change")
    schedule.add_argument("--every-hours", type=int, metavar="N", help="new interval (hours)")
    schedule.add_argument("--database-url", help="override DATABASE_URL")
    return parser


def _schedule(args: argparse.Namespace) -> int:
    if (args.retailer is None) != (args.every_hours is None):
        print("--retailer and --every-hours go together", file=sys.stderr)
        return 2
    if args.every_hours is not None and args.every_hours < 1:
        print("--every-hours must be >= 1", file=sys.stderr)
        return 2
    engine = make_engine(args.database_url)
    try:
        with make_session_factory(engine)() as session:
            if args.retailer is not None:
                retailer = session.scalars(
                    select(Retailer).where(Retailer.slug == args.retailer)
                ).one_or_none()
                if retailer is None:
                    print(f"Unknown retailer: {args.retailer}", file=sys.stderr)
                    return 2
                retailer.crawl_interval_hours = args.every_hours
                session.commit()
            retailers = session.scalars(select(Retailer).order_by(Retailer.slug)).all()
            if not retailers:
                print("No retailers in the database (run scripts/seed.py).")
            else:
                print("Times are UTC.")
            for r in retailers:
                last = (
                    r.last_crawled_at.strftime("%Y-%m-%d %H:%M") if r.last_crawled_at else "never"
                )
                due = next_due(r)
                due_text = due.strftime("%Y-%m-%d %H:%M") if due else "now"
                state = "" if r.is_active else "  (inactive)"
                print(
                    f"{r.slug:15} every {r.crawl_interval_hours:>3} h  last {last:16}  "
                    f"next {due_text}{state}"
                )
    finally:
        engine.dispose()
    return 0


async def _run(
    args: argparse.Namespace, slugs: list[str], fetcher_factory: FetcherFactory
) -> tuple[RunReport, dict[str, int] | None]:
    engine = make_engine(args.database_url)
    try:
        factory = make_session_factory(engine)
        async with fetcher_factory() as fetcher:
            report = await run_many(
                slugs,
                factory,
                fetcher,
                args.limit,
                include_inactive=args.include_inactive,
                due_only=args.due,
            )
        matched = None
        if args.match:
            with factory() as session:
                matched = dict(match_unmatched(session))
                session.commit()
        return report, matched
    finally:
        engine.dispose()


def main(argv: list[str] | None = None, fetcher_factory: FetcherFactory | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(args.verbose, args.log_format)
    spiders = load_spiders()

    if args.command == "list":
        if not spiders:
            print("No spiders registered yet.")
        for slug, cls in sorted(spiders.items()):
            print(f"{slug:15} {cls.name:25} {cls.base_url}")
        return 0
    if args.command == "schedule":
        return _schedule(args)

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
    report, matched = asyncio.run(_run(args, slugs, factory))
    for summary in report.summaries:
        print(summary.line())
    data = report.to_dict()
    if matched is not None:
        data["matching"] = matched
        print("matching: " + ", ".join(f"{k} {v}" for k, v in sorted(matched.items())))
    if args.summary_json:
        args.summary_json.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
