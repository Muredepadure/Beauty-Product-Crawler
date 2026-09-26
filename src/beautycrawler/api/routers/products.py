"""Product endpoints.

- `GET /api/products`: search the canonical product catalogue.
- `GET /api/products/{id}`: one product with every retailer's offer, cheapest flagged.
- `GET /api/products/{id}/history`: price history per retailer offer.

Search (`q`) is diacritic- and case-insensitive: every word of the query must occur in
the product's normalized name or its brand ("cremă effaclar" finds "Effaclar ... Crema").
`brand` accepts any known spelling or alias ("LRP", "la roche posay").
"""

import enum
import re
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import ColumnElement, Subquery, and_, case, func, or_, select
from sqlalchemy.orm import Session, selectinload

from beautycrawler.api.deps import get_session
from beautycrawler.api.schemas import (
    OfferOut,
    PricePoint,
    PriceSeries,
    ProductDetail,
    ProductHistory,
    ProductPage,
    ProductSummary,
    RetailerRef,
)
from beautycrawler.db.models import Brand, Offer, PriceHistory, Product
from beautycrawler.normalization.brands import brand_key, canonical_brand
from beautycrawler.normalization.text import fold

router = APIRouter(tags=["products"])

_WORD = re.compile(r"[0-9a-z]+")


class ProductSort(enum.StrEnum):
    NAME = "name"
    PRICE_ASC = "price_asc"
    PRICE_DESC = "price_desc"
    RETAILERS = "retailers"  # most retailers first


def search_words(q: str) -> list[str]:
    """Query words, folded; punctuation dropped ("L'Oréal Duo+" -> loreal, duo)."""
    return list(dict.fromkeys(_WORD.findall(fold(q).replace("'", ""))))


def _offer_stats() -> Subquery:
    """Per-product aggregates over linked offers."""
    in_stock_price = case((Offer.in_stock, Offer.price_bani))
    return (
        select(
            Offer.product_id,
            func.min(in_stock_price).label("lowest_price"),
            func.count(Offer.id).label("offer_count"),
            func.count(func.distinct(Offer.retailer_id)).label("retailer_count"),
            func.max(case((Offer.in_stock, 1), else_=0)).label("any_in_stock"),
        )
        .group_by(Offer.product_id)
        .subquery()
    )


def _categories_matching(session: Session, category: str) -> list[str]:
    """Stored category spellings equal to `category` ignoring case and diacritics."""
    wanted = fold(category)
    stored = session.scalars(
        select(Product.category).distinct().where(Product.category.is_not(None))
    )
    return [c for c in stored if c is not None and fold(c) == wanted]


@router.get("/products", response_model=ProductPage)
def list_products(
    session: Annotated[Session, Depends(get_session)],
    q: Annotated[str | None, Query(description="Words to find in product name or brand")] = None,
    brand: Annotated[str | None, Query(description="Exact brand (any known alias)")] = None,
    category: Annotated[str | None, Query(description="Exact category")] = None,
    sort: ProductSort = ProductSort.NAME,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 24,
) -> ProductPage:
    stats = _offer_stats()
    conditions = []
    if q:
        name_expr = Product.normalized_name  # already folded (lowercase, no diacritics)
        brand_expr = func.coalesce(Brand.normalized_name, "")
        for word in search_words(q):
            pattern = f"%{word}%"  # words are [0-9a-z]+, no LIKE wildcards to escape
            conditions.append(or_(name_expr.like(pattern), brand_expr.like(pattern)))
    if brand:
        conditions.append(Brand.normalized_name == brand_key(canonical_brand(brand) or brand))
    if category:
        conditions.append(Product.category.in_(_categories_matching(session, category)))

    base = (
        select(Product, Brand.name.label("brand_name"), stats)
        .outerjoin(Brand, Product.brand_id == Brand.id)
        .outerjoin(stats, stats.c.product_id == Product.id)
        .where(and_(True, *conditions))
    )
    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0

    no_price = case((stats.c.lowest_price.is_(None), 1), else_=0)  # unpriced last
    orders: dict[ProductSort, list[ColumnElement[Any]]] = {
        ProductSort.NAME: [Product.normalized_name.asc()],
        ProductSort.PRICE_ASC: [no_price, stats.c.lowest_price],
        ProductSort.PRICE_DESC: [no_price, stats.c.lowest_price.desc()],
        ProductSort.RETAILERS: [func.coalesce(stats.c.retailer_count, 0).desc()],
    }
    order = orders[sort]
    rows = session.execute(
        base.order_by(*order, Product.id).limit(page_size).offset((page - 1) * page_size)
    ).all()

    items = [
        ProductSummary(
            id=row.Product.id,
            name=row.Product.name,
            brand=row.brand_name,
            category=row.Product.category,
            size_value=row.Product.size_value,
            size_unit=row.Product.size_unit,
            ean=row.Product.ean,
            image_url=row.Product.image_url,
            lowest_price_bani=row.lowest_price,
            offer_count=row.offer_count or 0,
            retailer_count=row.retailer_count or 0,
            in_stock=bool(row.any_in_stock),
        )
        for row in rows
    ]
    return ProductPage(total=total, page=page, page_size=page_size, items=items)


@router.get(
    "/products/{product_id}",
    response_model=ProductDetail,
    responses={404: {"description": "No such product"}},
)
def get_product(
    session: Annotated[Session, Depends(get_session)],
    product_id: Annotated[int, Path(ge=1)],
) -> ProductDetail:
    product = session.scalars(
        select(Product)
        .where(Product.id == product_id)
        .options(
            selectinload(Product.brand),
            selectinload(Product.offers).selectinload(Offer.retailer),
        )
    ).one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    offers = sorted(product.offers, key=lambda o: (not o.in_stock, o.price_bani, o.id))
    in_stock_prices = [o.price_bani for o in offers if o.in_stock]
    lowest = min(in_stock_prices) if in_stock_prices else None
    return ProductDetail(
        id=product.id,
        name=product.name,
        brand=product.brand.name if product.brand else None,
        category=product.category,
        size_value=product.size_value,
        size_unit=product.size_unit,
        ean=product.ean,
        image_url=product.image_url,
        lowest_price_bani=lowest,
        offer_count=len(offers),
        retailer_count=len({o.retailer_id for o in offers}),
        in_stock=lowest is not None,
        offers=[
            OfferOut(
                id=o.id,
                retailer=RetailerRef(slug=o.retailer.slug, name=o.retailer.name),
                url=o.url,
                title=o.title,
                seller_name=o.seller_name,
                price_bani=o.price_bani,
                old_price_bani=o.old_price_bani,
                currency=o.currency,
                in_stock=o.in_stock,
                last_seen_at=o.last_seen_at,
                is_cheapest=o.in_stock and o.price_bani == lowest,
            )
            for o in offers
        ],
    )


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _window(history: list[PriceHistory], since: datetime | None) -> list[PriceHistory]:
    """Points at/after `since`, plus the one in effect at `since` (so a chart of the
    window starts at the right price)."""
    if since is None:
        return history
    before = [h for h in history if _as_utc(h.scraped_at) < since]
    inside = [h for h in history if _as_utc(h.scraped_at) >= since]
    return before[-1:] + inside


@router.get(
    "/products/{product_id}/history",
    response_model=ProductHistory,
    responses={404: {"description": "No such product"}},
)
def get_product_history(
    session: Annotated[Session, Depends(get_session)],
    product_id: Annotated[int, Path(ge=1)],
    days: Annotated[
        int | None, Query(ge=1, le=3650, description="Only the last N days (default: all)")
    ] = None,
) -> ProductHistory:
    product = session.scalars(
        select(Product)
        .where(Product.id == product_id)
        .options(
            selectinload(Product.offers).selectinload(Offer.retailer),
            selectinload(Product.offers).selectinload(Offer.history),
        )
    ).one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    since = datetime.now(UTC) - timedelta(days=days) if days is not None else None
    series = []
    for offer in sorted(product.offers, key=lambda o: (o.retailer.slug, o.id)):
        history = sorted(offer.history, key=lambda h: (_as_utc(h.scraped_at), h.id))
        series.append(
            PriceSeries(
                offer_id=offer.id,
                retailer=RetailerRef(slug=offer.retailer.slug, name=offer.retailer.name),
                seller_name=offer.seller_name,
                url=offer.url,
                last_seen_at=offer.last_seen_at,
                points=[
                    PricePoint(
                        scraped_at=h.scraped_at,
                        price_bani=h.price_bani,
                        old_price_bani=h.old_price_bani,
                        in_stock=h.in_stock,
                    )
                    for h in _window(history, since)
                ],
            )
        )
    return ProductHistory(product_id=product.id, series=series)
