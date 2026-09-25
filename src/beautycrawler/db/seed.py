"""Idempotent seed data: the tracked retailers (ROADMAP.md) and a few demo products.

Demo products are real product lines without EANs, offers or prices, so nothing
fabricated can be mistaken for scraped data.
"""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from beautycrawler.db.models import Brand, Product, Retailer
from beautycrawler.normalization.text import fold

# (slug, name, domain) — keep in sync with the retailer table in ROADMAP.md.
RETAILERS: tuple[tuple[str, str, str], ...] = (
    ("notino", "Notino", "notino.ro"),
    ("emag", "eMAG", "emag.ro"),
    ("sephora", "Sephora", "sephora.ro"),
    ("douglas", "Douglas", "douglas.ro"),
    ("makeup", "Makeup.ro", "makeup.ro"),
    ("dm", "dm drogerie markt", "dm.ro"),
    ("farmaciatei", "Farmacia Tei", "farmaciatei.ro"),
    ("drmax", "Dr.Max", "drmax.ro"),
    ("parfimo", "Parfimo", "parfimo.ro"),
    ("elefant", "Elefant", "elefant.ro"),
)

# (brand, product name, size, unit, category)
DEMO_PRODUCTS: tuple[tuple[str, str, str, str, str], ...] = (
    ("La Roche-Posay", "Effaclar Duo+", "40", "ml", "Îngrijirea tenului"),
    ("La Roche-Posay", "Cicaplast Baume B5+", "40", "ml", "Îngrijirea tenului"),
    ("CeraVe", "Hydrating Cleanser", "236", "ml", "Curățare"),
    ("Bioderma", "Sensibio H2O", "500", "ml", "Curățare"),
    ("The Ordinary", "Niacinamide 10% + Zinc 1%", "30", "ml", "Seruri"),
    ("L'Oréal Paris", "Revitalift Filler Hyaluronic Acid Serum", "30", "ml", "Seruri"),
)


@dataclass(frozen=True, slots=True)
class SeedResult:
    retailers_added: int
    brands_added: int
    products_added: int


def seed_retailers(session: Session) -> int:
    existing = set(session.scalars(select(Retailer.slug)))
    added = 0
    for slug, name, domain in RETAILERS:
        if slug not in existing:
            session.add(Retailer(slug=slug, name=name, domain=domain))
            added += 1
    return added


def seed_demo_products(session: Session) -> tuple[int, int]:
    brands = {b.normalized_name: b for b in session.scalars(select(Brand))}
    existing = {(p.brand_id, p.normalized_name) for p in session.scalars(select(Product))}
    brands_added = products_added = 0
    for brand_name, name, size, unit, category in DEMO_PRODUCTS:
        brand = brands.get(fold(brand_name))
        if brand is None:
            brand = Brand(name=brand_name, normalized_name=fold(brand_name))
            session.add(brand)
            session.flush()
            brands[brand.normalized_name] = brand
            brands_added += 1
        if (brand.id, fold(name)) in existing:
            continue
        session.add(
            Product(
                brand=brand,
                name=name,
                normalized_name=fold(name),
                size_value=Decimal(size),
                size_unit=unit,
                category=category,
            )
        )
        products_added += 1
    return brands_added, products_added


def seed(session: Session, *, demo: bool = True) -> SeedResult:
    """Insert missing seed rows and commit. Safe to run repeatedly."""
    retailers = seed_retailers(session)
    brands, products = seed_demo_products(session) if demo else (0, 0)
    session.commit()
    return SeedResult(retailers, brands, products)
