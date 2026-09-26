"""`ScrapedOffer`: what every spider's `parse_product` returns.

Validation is strict about things that would corrupt data (negative prices, non-http
URLs, unknown size units) and lenient about optional retailer data that is often
sloppy: an invalid EAN/GTIN becomes `None` instead of rejecting the whole offer.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from beautycrawler.db.repository import OfferSnapshot

SizeUnit = Literal["ml", "l", "g", "kg", "buc"]
GTIN_LENGTHS = (8, 12, 13, 14)


def gtin_is_valid(code: str) -> bool:
    """GS1 check digit for GTIN-8/12/13/14."""
    if not code.isdigit() or len(code) not in GTIN_LENGTHS:
        return False
    digits = [int(c) for c in code]
    body, check = digits[:-1], digits[-1]
    # Weights alternate 3,1,3,... starting from the digit next to the check digit.
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return (10 - total % 10) % 10 == check


def normalize_gtin(value: object) -> str | None:
    """Digits-only GTIN with a valid check digit, else None. GTIN-12/UPC keeps its form."""
    if value is None:
        return None
    code = "".join(str(value).split()).replace("-", "")
    return code if gtin_is_valid(code) else None


def _http_url(value: str) -> str:
    if not value.startswith(("http://", "https://")):
        raise ValueError("must be an absolute http(s) URL")
    return value


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


HttpUrlStr = Annotated[str, AfterValidator(_http_url)]


def _now() -> datetime:
    return datetime.now(UTC)


class ScrapedOffer(BaseModel):
    """One product page as seen on one retailer at one moment. Prices in bani."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True, extra="forbid")

    retailer: str = Field(min_length=1, description="Retailer slug, e.g. 'notino'")
    url: HttpUrlStr
    title: str = Field(min_length=1)
    price_bani: int = Field(ge=0)
    old_price_bani: int | None = Field(default=None, ge=0, description="Pre-sale price")
    currency: str = Field(default="RON", pattern=r"^[A-Z]{3}$")
    in_stock: bool
    brand: str | None = None
    ean: str | None = None
    size_value: Decimal | None = Field(default=None, gt=0)
    size_unit: SizeUnit | None = None
    image_url: HttpUrlStr | None = None
    seller_name: str | None = None  # marketplaces (eMAG)
    scraped_at: Annotated[datetime, AfterValidator(_utc)] = Field(default_factory=_now)

    @field_validator("ean", mode="before")
    @classmethod
    def _clean_ean(cls, value: object) -> str | None:
        return normalize_gtin(value)

    @field_validator("brand", "seller_name", mode="after")
    @classmethod
    def _empty_to_none(cls, value: str | None) -> str | None:
        return value or None

    @model_validator(mode="after")
    def _check_consistency(self) -> "ScrapedOffer":
        if (self.size_value is None) != (self.size_unit is None):
            raise ValueError("size_value and size_unit must be given together")
        if self.old_price_bani is not None and self.old_price_bani <= self.price_bani:
            # Not a discount (retailers sometimes repeat the price); drop it.
            object.__setattr__(self, "old_price_bani", None)
        return self

    @property
    def is_on_sale(self) -> bool:
        return self.old_price_bani is not None

    def to_snapshot(self) -> OfferSnapshot:
        """Convert to the DB write-path input (`db.repository.upsert_offer`)."""
        return OfferSnapshot(
            url=self.url,
            title=self.title,
            price_bani=self.price_bani,
            in_stock=self.in_stock,
            old_price_bani=self.old_price_bani,
            currency=self.currency,
            brand_name=self.brand,
            ean=self.ean,
            size_value=self.size_value,
            size_unit=self.size_unit,
            image_url=self.image_url,
            seller_name=self.seller_name,
        )
