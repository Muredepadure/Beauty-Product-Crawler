"""Core data model.

- `Retailer`: a tracked shop (notino.ro, ...).
- `Brand`: canonical brand; `normalized_name` is the matching key (see P4.1).
- `Product`: canonical item across retailers (brand + name + size, EAN when known).
- `Offer`: one retailer's listing (URL) with its latest price and stock. `product_id` is
  nullable because offers are stored as scraped and linked to a `Product` by matching (P4.4).
  eMAG can list one product from several sellers, so (product, retailer) is not unique;
  (retailer, url) is.
- `PriceHistory`: observations of an offer's price/stock over time.

All money is integer **bani** (1 RON = 100 bani).
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from beautycrawler.db.base import Base, TimestampMixin, utcnow

SIZE_UNITS = ("ml", "l", "g", "kg", "buc")


class Retailer(TimestampMixin, Base):
    __tablename__ = "retailers"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    domain: Mapped[str] = mapped_column(String(200), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    offers: Mapped[list["Offer"]] = relationship(back_populates="retailer")

    def __repr__(self) -> str:
        return f"Retailer(slug={self.slug!r})"


class Brand(TimestampMixin, Base):
    __tablename__ = "brands"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    normalized_name: Mapped[str] = mapped_column(String(200), unique=True)

    products: Mapped[list["Product"]] = relationship(back_populates="brand")

    def __repr__(self) -> str:
        return f"Brand(name={self.name!r})"


class Product(TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("size_value IS NULL OR size_value > 0", name="size_value_positive"),
        CheckConstraint(
            "size_unit IS NULL OR size_unit IN ('ml', 'l', 'g', 'kg', 'buc')",
            name="size_unit_known",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int | None] = mapped_column(
        ForeignKey("brands.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(String(500))
    normalized_name: Mapped[str] = mapped_column(String(500), index=True)
    size_value: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    size_unit: Mapped[str | None] = mapped_column(String(10))
    ean: Mapped[str | None] = mapped_column(String(14), unique=True)
    category: Mapped[str | None] = mapped_column(String(200))
    image_url: Mapped[str | None] = mapped_column(Text)

    brand: Mapped[Brand | None] = relationship(back_populates="products")
    offers: Mapped[list["Offer"]] = relationship(back_populates="product")

    def __repr__(self) -> str:
        return f"Product(id={self.id!r}, name={self.name!r})"


class Offer(TimestampMixin, Base):
    __tablename__ = "offers"
    __table_args__ = (
        UniqueConstraint("retailer_id", "url", name="uq_offers_retailer_id_url"),
        CheckConstraint("price_bani >= 0", name="price_non_negative"),
        CheckConstraint(
            "old_price_bani IS NULL OR old_price_bani >= 0", name="old_price_non_negative"
        ),
        CheckConstraint("size_value IS NULL OR size_value > 0", name="size_value_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    retailer_id: Mapped[int] = mapped_column(
        ForeignKey("retailers.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), index=True
    )
    url: Mapped[str] = mapped_column(String(2000))
    # Raw scraped fields, kept as the retailer shows them (inputs to matching).
    title: Mapped[str] = mapped_column(String(500))
    brand_name: Mapped[str | None] = mapped_column(String(200))
    ean: Mapped[str | None] = mapped_column(String(14), index=True)
    size_value: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    size_unit: Mapped[str | None] = mapped_column(String(10))
    image_url: Mapped[str | None] = mapped_column(Text)
    seller_name: Mapped[str | None] = mapped_column(String(200))  # marketplaces (eMAG)
    # Latest observation (denormalized from PriceHistory for fast listing queries).
    price_bani: Mapped[int] = mapped_column(Integer)
    old_price_bani: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="RON")
    in_stock: Mapped[bool] = mapped_column(Boolean, default=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    retailer: Mapped[Retailer] = relationship(back_populates="offers")
    product: Mapped[Product | None] = relationship(back_populates="offers")
    history: Mapped[list["PriceHistory"]] = relationship(
        back_populates="offer",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="PriceHistory.scraped_at",
    )

    def __repr__(self) -> str:
        return f"Offer(id={self.id!r}, url={self.url!r}, price_bani={self.price_bani!r})"


class PriceHistory(Base):
    __tablename__ = "price_history"
    __table_args__ = (
        CheckConstraint("price_bani >= 0", name="price_non_negative"),
        CheckConstraint(
            "old_price_bani IS NULL OR old_price_bani >= 0", name="old_price_non_negative"
        ),
        Index("ix_price_history_offer_id_scraped_at", "offer_id", "scraped_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    offer_id: Mapped[int] = mapped_column(ForeignKey("offers.id", ondelete="CASCADE"))
    price_bani: Mapped[int] = mapped_column(Integer)
    old_price_bani: Mapped[int | None] = mapped_column(Integer)
    in_stock: Mapped[bool] = mapped_column(Boolean)
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    offer: Mapped[Offer] = relationship(back_populates="history")

    def __repr__(self) -> str:
        return f"PriceHistory(offer_id={self.offer_id!r}, price_bani={self.price_bani!r})"
