"""Core data model.

- `Retailer`: a tracked shop (notino.ro, ...).
- `Brand`: canonical brand; `normalized_name` is `normalization.brands.brand_key()`.
- `Product`: canonical item across retailers (brand + name + size, EAN when known).
- `Offer`: one retailer's listing (URL) with its latest price and stock. `product_id` is
  nullable because offers are stored as scraped and linked to a `Product` by matching (P4.4).
  eMAG can list one product from several sellers, so (product, retailer) is not unique;
  (retailer, url) is.
- `PriceHistory`: observations of an offer's price/stock over time.
- `MatchCandidate`: an offer/product pair the matcher found plausible but not certain;
  a human approves or rejects it (review table, P4.4/P4.5).

All money is integer **bani** (1 RON = 100 bani).
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
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
MATCH_STATUSES = ("pending", "approved", "rejected")


class Retailer(TimestampMixin, Base):
    __tablename__ = "retailers"
    __table_args__ = (CheckConstraint("crawl_interval_hours > 0", name="crawl_interval_positive"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    domain: Mapped[str] = mapped_column(String(200), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Scheduling (P6.2): `crawl run --due` crawls a retailer once this many hours have
    # passed since its last successful crawl.
    crawl_interval_hours: Mapped[int] = mapped_column(Integer, default=24, server_default="24")
    last_crawled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

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
    # Complete crawls of the retailer in a row that didn't see this listing (P6.3);
    # reset when seen. At `settings.stale_after_runs` the offer is marked out of stock.
    missed_runs: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

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


class MatchCandidate(TimestampMixin, Base):
    """A possible offer -> product link awaiting (or after) human review.

    Rejected pairs are kept so re-running the matcher never proposes them again.
    """

    __tablename__ = "match_candidates"
    __table_args__ = (
        UniqueConstraint("offer_id", "product_id", name="uq_match_candidates_offer_id_product_id"),
        CheckConstraint("status IN ('pending', 'approved', 'rejected')", name="status_known"),
        CheckConstraint("score >= 0 AND score <= 100", name="score_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    offer_id: Mapped[int] = mapped_column(ForeignKey("offers.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    score: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(String(500))  # why it needs review
    status: Mapped[str] = mapped_column(String(10), default="pending", index=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    offer: Mapped[Offer] = relationship()
    product: Mapped[Product] = relationship()

    def __repr__(self) -> str:
        return (
            f"MatchCandidate(offer_id={self.offer_id!r}, product_id={self.product_id!r}, "
            f"score={self.score!r}, status={self.status!r})"
        )
