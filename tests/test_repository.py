from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from beautycrawler.db import Offer, PriceHistory, Retailer
from beautycrawler.db.repository import OfferSnapshot, UpsertOutcome, upsert_offer

T0 = datetime(2026, 9, 1, 3, 0, tzinfo=UTC)
URL = "https://www.notino.ro/la-roche-posay/effaclar-duo-plus/"

SNAP = OfferSnapshot(
    url=URL,
    title="La Roche-Posay Effaclar Duo+ 40 ml",
    price_bani=8999,
    in_stock=True,
    brand_name="La Roche-Posay",
    ean="3337875598996",
    size_value=Decimal("40"),
    size_unit="ml",
)


@pytest.fixture
def retailer(session: Session) -> Retailer:
    r = Retailer(slug="notino", name="Notino", domain="notino.ro")
    session.add(r)
    session.flush()
    return r


def history(session: Session) -> list[tuple[int, int | None, bool]]:
    rows = session.scalars(select(PriceHistory).order_by(PriceHistory.scraped_at)).all()
    return [(h.price_bani, h.old_price_bani, h.in_stock) for h in rows]


def offer_count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(Offer)) or 0


def test_create(session: Session, retailer: Retailer) -> None:
    result = upsert_offer(session, retailer, SNAP, T0)
    session.commit()
    assert result.outcome is UpsertOutcome.CREATED
    offer = result.offer
    assert offer.id is not None
    assert (offer.price_bani, offer.in_stock, offer.currency) == (8999, True, "RON")
    assert offer.ean == "3337875598996"
    assert offer.first_seen_at == offer.last_seen_at
    assert history(session) == [(8999, None, True)]


def test_same_price_and_stock_does_not_add_history(session: Session, retailer: Retailer) -> None:
    upsert_offer(session, retailer, SNAP, T0)
    result = upsert_offer(session, retailer, SNAP, T0 + timedelta(days=1))
    session.commit()
    assert result.outcome is UpsertOutcome.UNCHANGED
    assert history(session) == [(8999, None, True)]
    assert offer_count(session) == 1
    session.expire_all()
    offer = session.scalars(select(Offer)).one()
    assert offer.last_seen_at.replace(tzinfo=UTC) == T0 + timedelta(days=1)
    assert offer.first_seen_at.replace(tzinfo=UTC) == T0


def test_price_change_adds_history(session: Session, retailer: Retailer) -> None:
    upsert_offer(session, retailer, SNAP, T0)
    sale = replace(SNAP, price_bani=6999, old_price_bani=8999)
    result = upsert_offer(session, retailer, sale, T0 + timedelta(days=1))
    session.commit()
    assert result.outcome is UpsertOutcome.CHANGED
    assert (result.offer.price_bani, result.offer.old_price_bani) == (6999, 8999)
    assert history(session) == [(8999, None, True), (6999, 8999, True)]


def test_stock_change_adds_history(session: Session, retailer: Retailer) -> None:
    upsert_offer(session, retailer, SNAP, T0)
    result = upsert_offer(session, retailer, replace(SNAP, in_stock=False), T0 + timedelta(1))
    upsert_offer(session, retailer, replace(SNAP, in_stock=True), T0 + timedelta(2))
    session.commit()
    assert result.outcome is UpsertOutcome.CHANGED
    assert history(session) == [(8999, None, True), (8999, None, False), (8999, None, True)]


def test_price_back_to_previous_value_is_recorded(session: Session, retailer: Retailer) -> None:
    upsert_offer(session, retailer, SNAP, T0)
    upsert_offer(session, retailer, replace(SNAP, price_bani=7999), T0 + timedelta(1))
    upsert_offer(session, retailer, SNAP, T0 + timedelta(2))
    assert [p for p, _, _ in history(session)] == [8999, 7999, 8999]


def test_descriptive_fields_refreshed_but_not_erased(session: Session, retailer: Retailer) -> None:
    upsert_offer(session, retailer, SNAP, T0)
    renamed = replace(SNAP, title="Effaclar Duo(+) 40ml", ean=None, image_url="https://img/x.jpg")
    offer = upsert_offer(session, retailer, renamed, T0 + timedelta(1)).offer
    assert offer.title == "Effaclar Duo(+) 40ml"
    assert offer.image_url == "https://img/x.jpg"
    assert offer.ean == "3337875598996"  # None in the new snapshot doesn't wipe it


def test_sale_ending_clears_old_price(session: Session, retailer: Retailer) -> None:
    upsert_offer(session, retailer, replace(SNAP, price_bani=6999, old_price_bani=8999), T0)
    offer = upsert_offer(session, retailer, SNAP, T0 + timedelta(1)).offer
    assert offer.old_price_bani is None


def test_stale_observation_ignored(session: Session, retailer: Retailer) -> None:
    upsert_offer(session, retailer, SNAP, T0 + timedelta(days=2))
    old = replace(SNAP, price_bani=1000, title="old title")
    result = upsert_offer(session, retailer, old, T0)
    session.commit()
    assert result.outcome is UpsertOutcome.STALE
    assert (result.offer.price_bani, result.offer.title) == (8999, SNAP.title)
    assert history(session) == [(8999, None, True)]


def test_stale_check_after_reload_from_db(session: Session, retailer: Retailer) -> None:
    """SQLite returns naive datetimes; comparison with aware ones must still work."""
    upsert_offer(session, retailer, SNAP, T0 + timedelta(days=2))
    session.commit()
    session.expire_all()
    assert upsert_offer(session, retailer, SNAP, T0).outcome is UpsertOutcome.STALE
    assert upsert_offer(session, retailer, SNAP, T0 + timedelta(3)).outcome is (
        UpsertOutcome.UNCHANGED
    )


def test_naive_scraped_at_treated_as_utc(session: Session, retailer: Retailer) -> None:
    upsert_offer(session, retailer, SNAP, T0)
    naive_later = (T0 + timedelta(hours=1)).replace(tzinfo=None)
    assert upsert_offer(session, retailer, SNAP, naive_later).outcome is UpsertOutcome.UNCHANGED


def test_same_url_different_retailers_are_separate(session: Session, retailer: Retailer) -> None:
    other = Retailer(slug="sephora", name="Sephora", domain="sephora.ro")
    session.add(other)
    upsert_offer(session, retailer, SNAP, T0)
    result = upsert_offer(session, other, SNAP, T0)
    assert result.outcome is UpsertOutcome.CREATED
    assert offer_count(session) == 2


def test_default_scraped_at_is_now(session: Session, retailer: Retailer) -> None:
    before = datetime.now(UTC)
    offer = upsert_offer(session, retailer, SNAP).offer
    assert before <= offer.last_seen_at <= datetime.now(UTC)


def test_negative_price_rejected(session: Session, retailer: Retailer) -> None:
    with pytest.raises(ValueError, match="negative price"):
        upsert_offer(session, retailer, replace(SNAP, price_bani=-1), T0)
