"""API response models. Money is integer bani (1 RON = 100 bani), as in the database."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field


def _utc(value: datetime) -> datetime:
    # SQLite returns naive datetimes for timezone=True columns; they are stored as UTC.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


UtcDatetime = Annotated[datetime, AfterValidator(_utc)]


class ProductSummary(BaseModel):
    id: int
    name: str
    brand: str | None
    category: str | None
    size_value: Decimal | None = Field(description="Package size, e.g. 40")
    size_unit: str | None = Field(description="ml, l, g, kg or buc")
    ean: str | None
    image_url: str | None
    lowest_price_bani: int | None = Field(
        description="Cheapest current price among in-stock offers; null if none in stock"
    )
    currency: str = "RON"
    offer_count: int = Field(description="Listings linked to this product")
    retailer_count: int = Field(description="Distinct retailers with a listing")
    in_stock: bool = Field(description="At least one listing is in stock")


class ProductPage(BaseModel):
    total: int = Field(description="Matches across all pages")
    page: int
    page_size: int
    items: list[ProductSummary]


class RetailerRef(BaseModel):
    slug: str
    name: str


class OfferOut(BaseModel):
    id: int
    retailer: RetailerRef
    url: str
    title: str = Field(description="Title as the retailer shows it")
    seller_name: str | None = Field(description="Marketplace seller (eMAG), if any")
    price_bani: int
    old_price_bani: int | None = Field(description="Pre-sale price when on sale")
    currency: str
    in_stock: bool
    last_seen_at: UtcDatetime
    is_cheapest: bool = Field(description="Lowest price among in-stock offers (ties all flagged)")


class ProductDetail(ProductSummary):
    offers: list[OfferOut] = Field(
        description="In-stock offers by price, then out-of-stock offers by price"
    )


class PricePoint(BaseModel):
    scraped_at: UtcDatetime = Field(description="When this price/stock was first observed")
    price_bani: int
    old_price_bani: int | None
    in_stock: bool


class PriceSeries(BaseModel):
    offer_id: int
    retailer: RetailerRef
    seller_name: str | None
    url: str
    last_seen_at: UtcDatetime = Field(description="Last time the listing was crawled")
    points: list[PricePoint] = Field(
        description=(
            "Oldest first. A point is recorded only when price or stock changes, so each "
            "one holds until the next point (or `last_seen_at`): draw it as a step chart."
        )
    )


class ProductHistory(BaseModel):
    product_id: int
    series: list[PriceSeries] = Field(description="One per offer, by retailer slug")
