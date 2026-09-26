"""Seller view: `GET /api/compare?brand=X`.

For each of a brand's products that has offers, every retailer's price against the
market. The market is one price per retailer (its cheapest in-stock offer, so several
marketplace sellers don't outweigh a single shop): its minimum and median. Out-of-stock
listings are shown and compared, but don't set the market price.
"""

import statistics
from collections import defaultdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from beautycrawler.api.deps import get_session
from beautycrawler.api.schemas import (
    BrandComparison,
    ProductComparison,
    RetailerPosition,
    RetailerPrice,
    RetailerRef,
)
from beautycrawler.db.models import Brand, Offer, Product
from beautycrawler.normalization.brands import brand_key, canonical_brand

router = APIRouter(tags=["compare"])


def pct_diff(price: int, reference: int | None) -> float | None:
    """(price - reference) / reference in %, one decimal."""
    if not reference:
        return None
    return round((price - reference) * 100 / reference, 1)


def _retailer_prices(offers: list[Offer]) -> dict[int, tuple[Offer, bool]]:
    """retailer id -> (its representative offer, in stock). A retailer's cheapest
    in-stock offer wins; failing that, its cheapest out-of-stock one."""
    best: dict[int, tuple[Offer, bool]] = {}
    for offer in sorted(offers, key=lambda o: (not o.in_stock, o.price_bani, o.id)):
        best.setdefault(offer.retailer_id, (offer, offer.in_stock))
    return best


def compare_product(product: Product) -> ProductComparison:
    per_retailer = _retailer_prices(product.offers)
    market = [o.price_bani for o, in_stock in per_retailer.values() if in_stock]
    low = min(market) if market else None
    median = round(statistics.median(market)) if market else None
    prices = [
        RetailerPrice(
            retailer=RetailerRef(slug=o.retailer.slug, name=o.retailer.name),
            price_bani=o.price_bani,
            in_stock=in_stock,
            vs_min_pct=pct_diff(o.price_bani, low),
            vs_median_pct=pct_diff(o.price_bani, median),
            is_cheapest=in_stock and o.price_bani == low,
        )
        for o, in_stock in per_retailer.values()
    ]
    prices.sort(key=lambda p: (not p.in_stock, p.price_bani, p.retailer.slug))
    return ProductComparison(
        product_id=product.id,
        name=product.name,
        size_value=product.size_value,
        size_unit=product.size_unit,
        market_min_bani=low,
        market_median_bani=median,
        prices=prices,
    )


def _positions(comparisons: list[ProductComparison]) -> list[RetailerPosition]:
    listed: dict[str, int] = defaultdict(int)
    cheapest: dict[str, int] = defaultdict(int)
    vs_median: dict[str, list[float]] = defaultdict(list)
    refs: dict[str, RetailerRef] = {}
    for comparison in comparisons:
        for p in comparison.prices:
            slug = p.retailer.slug
            refs[slug] = p.retailer
            listed[slug] += 1
            cheapest[slug] += p.is_cheapest
            if p.in_stock and p.vs_median_pct is not None:
                vs_median[slug].append(p.vs_median_pct)
    return [
        RetailerPosition(
            retailer=refs[slug],
            products_listed=listed[slug],
            cheapest_count=cheapest[slug],
            avg_vs_median_pct=(
                round(statistics.fmean(vs_median[slug]), 1) if vs_median[slug] else None
            ),
        )
        for slug in sorted(refs)
    ]


@router.get(
    "/compare",
    response_model=BrandComparison,
    responses={404: {"description": "Unknown brand"}},
)
def compare_brand(
    session: Annotated[Session, Depends(get_session)],
    brand: Annotated[str, Query(min_length=1, description="Brand (any known alias)")],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> BrandComparison:
    key = brand_key(canonical_brand(brand) or brand)
    found = session.scalars(select(Brand).where(Brand.normalized_name == key)).one_or_none()
    if found is None:
        raise HTTPException(status_code=404, detail="Brand not found")
    products = session.scalars(
        select(Product)
        .where(Product.brand_id == found.id, Product.offers.any())
        .options(selectinload(Product.offers).selectinload(Offer.retailer))
        .order_by(Product.normalized_name, Product.id)
    ).all()
    # Positions cover every product, so all are compared; the page slices the list.
    comparisons = [compare_product(p) for p in products]
    start = (page - 1) * page_size
    return BrandComparison(
        brand=found.name,
        retailers=_positions(comparisons),
        total=len(comparisons),
        page=page,
        page_size=page_size,
        products=comparisons[start : start + page_size],
    )
