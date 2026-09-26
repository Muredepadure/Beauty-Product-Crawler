"""Reference lists: `GET /api/retailers` and `GET /api/brands`."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from beautycrawler.api.deps import get_session
from beautycrawler.api.routers.products import search_words
from beautycrawler.api.schemas import BrandOut, BrandPage, RetailerOut
from beautycrawler.db.models import Brand, Offer, Product, Retailer

router = APIRouter(tags=["catalog"])


@router.get("/retailers", response_model=list[RetailerOut])
def list_retailers(
    session: Annotated[Session, Depends(get_session)],
    active: Annotated[
        bool | None, Query(description="Only active (true) or inactive (false) retailers")
    ] = None,
) -> list[RetailerOut]:
    """All tracked retailers by name (a short list, so not paginated)."""
    stats = (
        select(
            Offer.retailer_id,
            func.count(Offer.id).label("offer_count"),
            func.count(func.distinct(Offer.product_id)).label("product_count"),
        )
        .group_by(Offer.retailer_id)
        .subquery()
    )
    query = select(Retailer, stats.c.offer_count, stats.c.product_count).outerjoin(
        stats, stats.c.retailer_id == Retailer.id
    )
    if active is not None:
        query = query.where(Retailer.is_active.is_(active))
    rows = session.execute(query.order_by(func.lower(Retailer.name), Retailer.id)).all()
    return [
        RetailerOut(
            slug=r.Retailer.slug,
            name=r.Retailer.name,
            domain=r.Retailer.domain,
            is_active=r.Retailer.is_active,
            offer_count=r.offer_count or 0,
            product_count=r.product_count or 0,  # COUNT(DISTINCT) skips unmatched offers
        )
        for r in rows
    ]


@router.get("/brands", response_model=BrandPage)
def list_brands(
    session: Annotated[Session, Depends(get_session)],
    q: Annotated[str | None, Query(description="Words to find in the brand name")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> BrandPage:
    """Brands by name, with how many products each has."""
    counts = (
        select(Product.brand_id, func.count(Product.id).label("product_count"))
        .group_by(Product.brand_id)
        .subquery()
    )
    conditions = [Brand.normalized_name.like(f"%{w}%") for w in search_words(q or "")]
    base = (
        select(Brand, counts.c.product_count)
        .outerjoin(counts, counts.c.brand_id == Brand.id)
        .where(and_(True, *conditions))
    )
    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = session.execute(
        base.order_by(Brand.normalized_name, Brand.id)
        .limit(page_size)
        .offset((page - 1) * page_size)
    ).all()
    items = [
        BrandOut(id=r.Brand.id, name=r.Brand.name, product_count=r.product_count or 0) for r in rows
    ]
    return BrandPage(total=total, page=page, page_size=page_size, items=items)
