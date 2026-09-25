from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import Engine, delete, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from beautycrawler.db import Brand, Offer, PriceHistory, Product, Retailer


@pytest.fixture
def notino(session: Session) -> Retailer:
    r = Retailer(slug="notino", name="Notino", domain="notino.ro")
    session.add(r)
    session.flush()
    return r


def make_offer(retailer: Retailer, **kw: object) -> Offer:
    defaults: dict[str, object] = {
        "retailer": retailer,
        "url": "https://www.notino.ro/la-roche-posay/effaclar-duo/",
        "title": "La Roche-Posay Effaclar Duo+ 40 ml",
        "price_bani": 8999,
    }
    defaults.update(kw)
    return Offer(**defaults)


def test_tables_created(engine: Engine) -> None:
    assert set(inspect(engine).get_table_names()) == {
        "retailers",
        "brands",
        "products",
        "offers",
        "price_history",
    }


def test_full_graph_roundtrip(session: Session, notino: Retailer) -> None:
    brand = Brand(name="La Roche-Posay", normalized_name="la roche-posay")
    product = Product(
        brand=brand,
        name="Effaclar Duo+",
        normalized_name="effaclar duo+",
        size_value=Decimal("40"),
        size_unit="ml",
        ean="3337875598996",
    )
    t0 = datetime(2026, 9, 1, tzinfo=UTC)
    offer = make_offer(notino, product=product, old_price_bani=10999, in_stock=True)
    offer.history.append(PriceHistory(price_bani=10999, in_stock=True, scraped_at=t0))
    offer.history.append(
        PriceHistory(
            price_bani=8999, old_price_bani=10999, in_stock=True, scraped_at=t0 + timedelta(1)
        )
    )
    session.add(offer)
    session.commit()
    session.expire_all()

    loaded = session.scalars(select(Product).where(Product.ean == "3337875598996")).one()
    assert loaded.brand is not None and loaded.brand.name == "La Roche-Posay"
    assert loaded.size_value == Decimal("40.000")
    [o] = loaded.offers
    assert o.retailer.slug == "notino"
    assert o.currency == "RON"
    assert (o.price_bani, o.old_price_bani) == (8999, 10999)
    assert [h.price_bani for h in o.history] == [10999, 8999]  # ordered by scraped_at
    assert o.first_seen_at is not None and o.created_at is not None


def test_offer_without_product_allowed(session: Session, notino: Retailer) -> None:
    session.add(make_offer(notino))
    session.commit()
    assert session.scalars(select(Offer)).one().product_id is None


def test_offer_url_unique_per_retailer(session: Session, notino: Retailer) -> None:
    other = Retailer(slug="sephora", name="Sephora", domain="sephora.ro")
    session.add_all([make_offer(notino), make_offer(other)])  # same URL, different shop: ok
    session.commit()
    session.add(make_offer(notino))
    with pytest.raises(IntegrityError):
        session.commit()


@pytest.mark.parametrize(
    "bad",
    [
        {"price_bani": -1},
        {"old_price_bani": -5},
        {"size_value": Decimal("0")},
    ],
)
def test_offer_check_constraints(
    session: Session, notino: Retailer, bad: dict[str, object]
) -> None:
    session.add(make_offer(notino, **bad))
    with pytest.raises(IntegrityError):
        session.commit()


def test_product_unknown_unit_rejected(session: Session) -> None:
    session.add(Product(name="X", normalized_name="x", size_value=Decimal(1), size_unit="oz"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_product_ean_unique(session: Session) -> None:
    session.add_all(
        [
            Product(name="A", normalized_name="a", ean="5900000000001"),
            Product(name="B", normalized_name="b", ean="5900000000001"),
        ]
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_deleting_offer_deletes_history_at_db_level(session: Session, notino: Retailer) -> None:
    offer = make_offer(notino)
    offer.history.append(PriceHistory(price_bani=8999, in_stock=True))
    session.add(offer)
    session.commit()
    # Bulk delete (no ORM cascade): only the DB's ON DELETE CASCADE can remove history.
    session.execute(delete(Offer))
    session.commit()
    assert session.scalars(select(PriceHistory)).all() == []


def test_deleting_product_unlinks_offers(session: Session, notino: Retailer) -> None:
    product = Product(name="P", normalized_name="p")
    session.add(make_offer(notino, product=product))
    session.commit()
    session.execute(delete(Product))
    session.commit()
    session.expire_all()
    assert session.scalars(select(Offer)).one().product_id is None


def test_brand_normalized_name_unique(session: Session) -> None:
    session.add_all(
        [
            Brand(name="L'Oréal Paris", normalized_name="l'oreal paris"),
            Brand(name="L'Oreal Paris", normalized_name="l'oreal paris"),
        ]
    )
    with pytest.raises(IntegrityError):
        session.commit()
