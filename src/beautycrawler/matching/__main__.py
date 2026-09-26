"""Matching admin CLI.

    python -m beautycrawler.matching run [--limit N] [--no-create]
    python -m beautycrawler.matching list [--status pending|approved|rejected|all] [--limit N]
    python -m beautycrawler.matching approve CANDIDATE_ID
    python -m beautycrawler.matching reject CANDIDATE_ID [CANDIDATE_ID ...] [--no-rematch]

`run` links unmatched offers to products (EAN, then fuzzy); unclear cases become
candidates for `list` / `approve` / `reject`. The database schema must exist
(`alembic upgrade head`).
"""

import argparse
import sys
from decimal import Decimal

from sqlalchemy.orm import Session

from beautycrawler.db.models import MATCH_STATUSES, MatchCandidate, Offer, Product
from beautycrawler.db.session import make_engine, make_session_factory
from beautycrawler.matching.review import (
    ReviewError,
    approve_candidate,
    list_candidates,
    reject_candidate,
)
from beautycrawler.matching.service import MatchConfig, match_unmatched


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m beautycrawler.matching")
    parser.add_argument("--database-url", help="override DATABASE_URL")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="match offers that have no product yet")
    run.add_argument("--limit", type=int, help="max offers to process")
    run.add_argument(
        "--no-create", action="store_true", help="don't create products for unmatched offers"
    )

    lst = sub.add_parser("list", help="show match candidates")
    lst.add_argument("--status", choices=[*MATCH_STATUSES, "all"], default="pending")
    lst.add_argument("--limit", type=int, help="max rows")

    approve = sub.add_parser("approve", help="link the candidate's offer to its product")
    approve.add_argument("candidate_id", type=int)

    reject = sub.add_parser("reject", help="mark candidates as different products")
    reject.add_argument("candidate_ids", type=int, nargs="+", metavar="CANDIDATE_ID")
    reject.add_argument(
        "--no-rematch",
        action="store_true",
        help="leave the offer unmatched when its last candidate is rejected",
    )
    return parser


def _size(value: Decimal | None, unit: str | None) -> str:
    return f"{value.normalize():f} {unit}" if value is not None and unit else "?"


def _describe_offer(offer: Offer) -> str:
    return (
        f"offer {offer.id} [{offer.retailer.slug}] {offer.title!r} "
        f"({_size(offer.size_value, offer.size_unit)}, EAN {offer.ean or '-'})\n"
        f"  {offer.url}"
    )


def _describe_product(product: Product) -> str:
    brand = product.brand.name if product.brand else "?"
    return (
        f"product {product.id}: {brand} {product.name!r} "
        f"({_size(product.size_value, product.size_unit)}, EAN {product.ean or '-'})"
    )


def _print_candidates(candidates: list[MatchCandidate]) -> None:
    if not candidates:
        print("No match candidates.")
        return
    offer_id = None
    for c in candidates:
        if c.offer_id != offer_id:
            offer_id = c.offer_id
            print(_describe_offer(c.offer))
        print(
            f"  #{c.id:<5} {c.score:5.1f}  {c.status:8}  -> {_describe_product(c.product)}\n"
            f"         why review: {c.reason}"
        )


def _run_command(args: argparse.Namespace, session: Session) -> int:
    if args.command == "run":
        counts = match_unmatched(
            session, MatchConfig(create_products=not args.no_create), limit=args.limit
        )
        session.commit()
        if not counts:
            print("No unmatched offers.")
        for method, n in sorted(counts.items()):
            print(f"{method:16} {n}")
        return 0

    if args.command == "list":
        status = None if args.status == "all" else args.status
        _print_candidates(list_candidates(session, status, args.limit))
        return 0

    if args.command == "approve":
        candidate = approve_candidate(session, args.candidate_id)
        session.commit()
        c = candidate
        print(f"Approved #{c.id}: offer {c.offer_id} -> product {c.product_id}")
        return 0

    # reject: all ids or none (an error rolls back the whole command)
    lines = []
    for candidate_id in dict.fromkeys(args.candidate_ids):
        result = reject_candidate(session, candidate_id, rematch=not args.no_rematch)
        line = f"Rejected #{candidate_id}"
        if result.rematch is not None:
            rematch = result.rematch
            line += f"; offer {result.candidate.offer_id} re-matched: {rematch.method.value}"
            if rematch.product is not None:
                line += f" -> product {rematch.product.id}"
        lines.append(line)
    session.commit()
    print("\n".join(lines))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "limit", None) is not None and args.limit < 1:
        print("--limit must be >= 1", file=sys.stderr)
        return 2
    engine = make_engine(args.database_url)
    try:
        with make_session_factory(engine)() as session:
            try:
                return _run_command(args, session)
            except ReviewError as exc:
                session.rollback()
                print(f"error: {exc}", file=sys.stderr)
                return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
