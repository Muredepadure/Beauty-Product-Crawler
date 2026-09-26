"""`GET /api/price-drops`: listings whose price just fell (foundation for alerts)."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from beautycrawler.api.deps import get_session
from beautycrawler.api.schemas import PriceDropList, PriceDropOut, ProductRef, RetailerRef
from beautycrawler.db.price_drops import find_price_drops

router = APIRouter(tags=["alerts"])


@router.get("/price-drops", response_model=PriceDropList)
def price_drops(
    session: Annotated[Session, Depends(get_session)],
    min_pct: Annotated[
        float, Query(gt=0, le=100, description="Minimum cut vs the previous price, in %")
    ] = 10.0,
    hours: Annotated[
        int, Query(ge=1, le=24 * 90, description="Only changes in the last N hours")
    ] = 24,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> PriceDropList:
    """In-stock listings whose latest price change was a cut of at least `min_pct` %."""
    since = datetime.now(UTC) - timedelta(hours=hours)
    drops = find_price_drops(session, min_pct=min_pct, since=since, limit=limit)
    items = []
    for d in drops:
        o = d.offer
        product = o.product
        items.append(
            PriceDropOut(
                offer_id=o.id,
                product=ProductRef(
                    id=product.id,
                    name=product.name,
                    brand=product.brand.name if product.brand else None,
                )
                if product is not None
                else None,
                retailer=RetailerRef(slug=o.retailer.slug, name=o.retailer.name),
                title=o.title,
                url=o.url,
                previous_price_bani=d.previous_price_bani,
                price_bani=d.price_bani,
                drop_pct=d.drop_pct,
                changed_at=d.changed_at,
            )
        )
    return PriceDropList(min_pct=min_pct, since=since, items=items)
