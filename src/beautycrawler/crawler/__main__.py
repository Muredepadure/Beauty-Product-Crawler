"""Crawl CLI.

    python -m beautycrawler.crawler list
    python -m beautycrawler.crawler run --retailer notino [--limit N]
    python -m beautycrawler.crawler run --all [--limit N]
    python -m beautycrawler.crawler run --all --due      # hourly cron entry point
    python -m beautycrawler.crawler schedule [--retailer SLUG --every-hours N]

Options for `run`: `--due` skips retailers crawled within their interval;
`--match` links offers to products before the crawl (left over from an interrupted run),
every few minutes during it and afterwards; `--keep-awake` stops Windows from sleeping
while the run lasts; `--only-brands wella,loreal` fetches only those brands' products
(by URL, checked again on the page; other products' prices are left as they are);
`--summary-json PATH` writes the run report; `--include-inactive` also crawls retailers
marked inactive in the database. `--log-format json` (before the command) gives one JSON
log object per line. Exit code 1 when any retailer failed.

The database schema must exist (`alembic upgrade head`).
"""

import argparse
import asyncio
import json
import sys
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from beautycrawler.config import get_settings
from beautycrawler.crawler.awake import keep_awake
from beautycrawler.crawler.fetcher import PoliteFetcher
from beautycrawler.crawler.runner import RunReport, load_spiders, next_due, run_many
from beautycrawler.db.models import Retailer
from beautycrawler.db.session import make_engine, make_session_factory
from beautycrawler.logs import configure_logging
from beautycrawler.matching.service import MatchMethod, match_unmatched

FetcherFactory = Callable[[], PoliteFetcher]
STILL_WAITING = (MatchMethod.AWAITING_REVIEW.value, MatchMethod.UNMATCHED.value)


def deadline_from(until: str, now: datetime | None = None) -> float:
    """`time.monotonic()` value at `until`: a local `HH:MM` (the next one: today, or
    tomorrow if past) or a local date and time `YYYY-MM-DDTHH:MM` (may be in the past:
    the deadline has then passed already). Several runs that must end at the same time
    take the date form, so a run that starts just after it doesn't go on until the
    next day."""
    now = now or datetime.now().astimezone()
    if "T" in until:
        target = datetime.fromisoformat(until)
        target = target.astimezone() if target.tzinfo is None else target
    else:
        hour, minute = (int(part) for part in until.split(":", 1))
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
    return time.monotonic() + (target - now).total_seconds()


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
    run.add_argument(
        "--match", action="store_true", help="link new offers to products (also during the run)"
    )
    run.add_argument(
        "--only-brands",
        metavar="B1,B2",
        help="only products of these brands, comma-separated (e.g. wella,loreal,kerastase)",
    )
    run.add_argument(
        "--keep-awake", action="store_true", help="keep Windows from sleeping during the run"
    )
    run.add_argument("--summary-json", type=Path, metavar="PATH", help="write the run report")
    run.add_argument(
        "--include-inactive", action="store_true", help="also crawl retailers marked inactive"
    )
    run.add_argument(
        "--due", action="store_true", help="only retailers whose crawl interval has passed"
    )
    run.add_argument(
        "--skip-seen-hours",
        type=float,
        metavar="H",
        help="skip pages whose listing was seen in the last H hours (continue a long crawl)",
    )
    run.add_argument(
        "--until",
        metavar="HH:MM",
        help="local time (HH:MM or YYYY-MM-DDTHH:MM) to stop, between pages; retailers "
        "not reached are skipped",
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
        matched: dict[str, int] | None = None
        on_progress = None
        if args.match:
            matched = {}

            def link(session: Session) -> None:
                counts = match_unmatched(session)
                # Offers still waiting are seen again on every pass: report the latest
                # count for those, and add up the links actually made.
                for method in STILL_WAITING:
                    matched.pop(method, None)
                for method, n in counts.items():
                    matched[method] = matched.get(method, 0) + n

            on_progress = link
            with factory() as session:  # offers an interrupted run left unlinked
                link(session)
                session.commit()
        async with fetcher_factory() as fetcher:
            report = await run_many(
                slugs,
                factory,
                fetcher,
                args.limit,
                include_inactive=args.include_inactive,
                due_only=args.due,
                skip_seen_hours=args.skip_seen_hours,
                deadline=args.deadline,
                on_progress=on_progress,
                brands=args.brands,
            )
        if on_progress is not None:
            with factory() as session:
                on_progress(session)
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
    if args.skip_seen_hours is not None and args.skip_seen_hours <= 0:
        print("--skip-seen-hours must be > 0", file=sys.stderr)
        return 2
    try:
        args.deadline = deadline_from(args.until) if args.until else None
    except ValueError:
        print("--until must be a time like 07:00 or 2026-10-30T07:00", file=sys.stderr)
        return 2
    args.brands = tuple(b.strip() for b in (args.only_brands or "").split(",") if b.strip())
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
    with keep_awake(args.keep_awake):
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
