"""Seed the database with the tracked retailers and a few demo products.

Usage:
    python scripts/seed.py              # uses DATABASE_URL (run `alembic upgrade head` first)
    python scripts/seed.py --no-demo    # retailers only
"""

import argparse

from beautycrawler.db.seed import seed
from beautycrawler.db.session import make_engine, make_session_factory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--database-url", help="override DATABASE_URL")
    parser.add_argument(
        "--no-demo", dest="demo", action="store_false", help="skip demo brands/products"
    )
    args = parser.parse_args(argv)

    engine = make_engine(args.database_url)
    try:
        with make_session_factory(engine)() as session:
            result = seed(session, demo=args.demo)
    finally:
        engine.dispose()
    print(
        f"Seeded: {result.retailers_added} retailers, {result.brands_added} brands, "
        f"{result.products_added} products (existing rows left untouched)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
