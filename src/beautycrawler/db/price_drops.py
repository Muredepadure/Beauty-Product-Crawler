"""Price-drop detection (P6.4), the foundation for alerts.

A drop is an offer's latest price change compared with its previous recorded price.
History rows are written only on price/stock changes (see `repository`), so "the
previous row" is the price before the latest change. Only in-stock listings count: a
cheaper price you can't buy is not a deal.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased, joinedload

from beautycrawler.db.models import Offer, PriceHistory, Product


@dataclass(frozen=True, slots=True)
class PriceDrop:
    offer: Offer
    previous_price_bani: int
    price_bani: int
    changed_at: datetime  # UTC

    @property
    def drop_pct(self) -> float:
        return round(
            (self.previous_price_bani - self.price_bani) * 100 / self.previous_price_bani, 1
        )


def find_price_drops(
    session: Session, *, min_pct: float, since: datetime, limit: int | None = None
) -> list[PriceDrop]:
    """In-stock offers whose latest change, at or after `since`, cut the price by at
    least `min_pct` %. Biggest drops first."""
    ranked = select(
        PriceHistory.offer_id,
        PriceHistory.price_bani,
        PriceHistory.in_stock,
        PriceHistory.scraped_at,
        func.row_number()
        .over(
            partition_by=PriceHistory.offer_id,
            order_by=(PriceHistory.scraped_at.desc(), PriceHistory.id.desc()),
        )
        .label("rn"),
    ).subquery()
    latest = aliased(ranked, name="latest")
    previous = aliased(ranked, name="previous")
    drop = previous.c.price_bani - latest.c.price_bani
    query = (
        select(Offer, previous.c.price_bani, latest.c.price_bani, latest.c.scraped_at)
        .options(joinedload(Offer.retailer), joinedload(Offer.product).joinedload(Product.brand))
        .join(latest, (latest.c.offer_id == Offer.id) & (latest.c.rn == 1))
        .join(previous, (previous.c.offer_id == Offer.id) & (previous.c.rn == 2))
        .where(
            latest.c.in_stock.is_(True),
            Offer.in_stock.is_(True),
            latest.c.scraped_at >= since.astimezone(UTC),  # stored as UTC
            drop > 0,
            drop * 100 >= min_pct * previous.c.price_bani,
        )
        .order_by((drop * 1.0 / previous.c.price_bani).desc(), Offer.id)
    )
    if limit is not None:
        query = query.limit(limit)
    return [
        PriceDrop(
            offer=offer,
            previous_price_bani=prev,
            price_bani=price,
            changed_at=at.replace(tzinfo=UTC) if at.tzinfo is None else at.astimezone(UTC),
        )
        for offer, prev, price, at in session.execute(query).all()
    ]
