"""API response models. Money is integer bani (1 RON = 100 bani), as in the database."""

from decimal import Decimal

from pydantic import BaseModel, Field


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
