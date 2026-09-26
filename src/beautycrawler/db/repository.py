"""Write path for scraped offers.

`upsert_offer` stores one observation of a retailer listing:

- new (retailer, url) → create the `Offer` and its first `PriceHistory` row;
- known offer → refresh descriptive fields and `last_seen_at`; append a `PriceHistory`
  row **only** when the price or stock status changed;
- observation older than the offer's `last_seen_at` (e.g. a delayed retry) → ignored,
  so it can't overwrite newer data.

`record_missed` is the other half (P6.3): after a complete crawl, listings the crawl
didn't see count a miss; at `stale_after` misses in a row they are marked out of stock
(with a history row, so charts show when they became unavailable).
"""

import enum
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from beautycrawler.db.base import utcnow
from beautycrawler.db.models import Offer, PriceHistory, Retailer


@dataclass(frozen=True, slots=True)
class OfferSnapshot:
    """One scraped observation of a listing (prices in bani)."""

    url: str
    title: str
    price_bani: int
    in_stock: bool
    old_price_bani: int | None = None
    currency: str = "RON"
    brand_name: str | None = None
    ean: str | None = None
    size_value: Decimal | None = None
    size_unit: str | None = None
    image_url: str | None = None
    seller_name: str | None = None


class UpsertOutcome(enum.Enum):
    CREATED = "created"
    CHANGED = "changed"  # price or stock changed; history row appended
    UNCHANGED = "unchanged"  # seen again, same price and stock
    STALE = "stale"  # older than what we already have; ignored


@dataclass(frozen=True, slots=True)
class UpsertResult:
    offer: Offer
    outcome: UpsertOutcome


# Descriptive fields refreshed from each snapshot (a missing value keeps the stored one).
_DESCRIPTIVE_FIELDS = (
    "title",
    "brand_name",
    "ean",
    "size_value",
    "size_unit",
    "image_url",
    "seller_name",
)


def _as_utc(dt: datetime) -> datetime:
    # SQLite hands back naive datetimes even for timezone=True columns; they are UTC.
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def get_offer(session: Session, retailer: Retailer, url: str) -> Offer | None:
    return session.scalars(
        select(Offer).where(Offer.retailer_id == retailer.id, Offer.url == url)
    ).one_or_none()


def upsert_offer(
    session: Session,
    retailer: Retailer,
    snapshot: OfferSnapshot,
    scraped_at: datetime | None = None,
) -> UpsertResult:
    """Insert or update an offer from a scraped snapshot. Flushes; does not commit."""
    if snapshot.price_bani < 0:
        raise ValueError(f"negative price for {snapshot.url}: {snapshot.price_bani}")
    seen = _as_utc(scraped_at) if scraped_at is not None else utcnow()

    offer = get_offer(session, retailer, snapshot.url)
    if offer is None:
        offer = Offer(
            retailer=retailer,
            url=snapshot.url,
            price_bani=snapshot.price_bani,
            old_price_bani=snapshot.old_price_bani,
            currency=snapshot.currency,
            in_stock=snapshot.in_stock,
            first_seen_at=seen,
            last_seen_at=seen,
            **{f: getattr(snapshot, f) for f in _DESCRIPTIVE_FIELDS},
        )
        offer.history.append(_history_row(snapshot, seen))
        session.add(offer)
        session.flush()
        return UpsertResult(offer, UpsertOutcome.CREATED)

    if seen < _as_utc(offer.last_seen_at):
        return UpsertResult(offer, UpsertOutcome.STALE)

    for field in _DESCRIPTIVE_FIELDS:
        value = getattr(snapshot, field)
        if value is not None:
            setattr(offer, field, value)
    offer.last_seen_at = seen
    offer.missed_runs = 0
    offer.old_price_bani = snapshot.old_price_bani
    offer.currency = snapshot.currency

    changed = offer.price_bani != snapshot.price_bani or offer.in_stock != snapshot.in_stock
    if changed:
        offer.price_bani = snapshot.price_bani
        offer.in_stock = snapshot.in_stock
        offer.history.append(_history_row(snapshot, seen))
    session.flush()
    return UpsertResult(offer, UpsertOutcome.CHANGED if changed else UpsertOutcome.UNCHANGED)


def _history_row(snapshot: OfferSnapshot, seen: datetime) -> PriceHistory:
    return PriceHistory(
        price_bani=snapshot.price_bani,
        old_price_bani=snapshot.old_price_bani,
        in_stock=snapshot.in_stock,
        scraped_at=seen,
    )


@dataclass(frozen=True, slots=True)
class MissedResult:
    missed: int  # listings not seen by this crawl
    marked_out_of_stock: int  # of those, newly marked out of stock


def record_missed(
    session: Session,
    retailer: Retailer,
    crawl_started_at: datetime,
    stale_after: int,
    now: datetime | None = None,
) -> MissedResult:
    """Count a miss for the retailer's offers not seen since `crawl_started_at`.

    Call only after a *complete* crawl (not a `--limit` sample or a failed run).
    Flushes; does not commit.
    """
    if stale_after < 1:
        raise ValueError("stale_after must be >= 1")
    started = _as_utc(crawl_started_at)
    at = _as_utc(now) if now is not None else utcnow()
    missed = marked = 0
    for offer in session.scalars(select(Offer).where(Offer.retailer_id == retailer.id)):
        if _as_utc(offer.last_seen_at) >= started:
            continue
        missed += 1
        offer.missed_runs += 1
        if offer.missed_runs >= stale_after and offer.in_stock:
            offer.in_stock = False
            offer.history.append(
                PriceHistory(
                    price_bani=offer.price_bani,
                    old_price_bani=offer.old_price_bani,
                    in_stock=False,
                    scraped_at=at,
                )
            )
            marked += 1
    session.flush()
    return MissedResult(missed, marked)
