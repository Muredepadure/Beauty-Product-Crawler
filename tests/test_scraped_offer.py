from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from beautycrawler.crawler.scraped import ScrapedOffer, gtin_is_valid, normalize_gtin
from beautycrawler.db import Retailer
from beautycrawler.db.repository import UpsertOutcome, upsert_offer

BASE: dict[str, Any] = {
    "retailer": "notino",
    "url": "https://www.notino.ro/la-roche-posay/effaclar-duo-plus/",
    "title": "  La Roche-Posay Effaclar Duo+ 40 ml ",
    "price_bani": 8999,
    "in_stock": True,
}


def make(**kw: Any) -> ScrapedOffer:
    return ScrapedOffer(**{**BASE, **kw})


def test_minimal_offer_defaults() -> None:
    offer = make()
    assert offer.title == "La Roche-Posay Effaclar Duo+ 40 ml"  # stripped
    assert offer.currency == "RON"
    assert offer.old_price_bani is None and not offer.is_on_sale
    assert offer.scraped_at.tzinfo is not None
    assert abs(datetime.now(UTC) - offer.scraped_at) < timedelta(seconds=5)


def test_full_offer() -> None:
    offer = make(
        old_price_bani=10999,
        brand="La Roche-Posay",
        ean="3337875598996",
        size_value="40",
        size_unit="ml",
        image_url="https://cdn.notino.ro/x.jpg",
    )
    assert offer.is_on_sale
    assert offer.size_value == Decimal("40")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("3337875598996", "3337875598996"),
        (" 3337 8755 98996 ", "3337875598996"),
        ("4006381-333931", "4006381333931"),
        (4006381333931, "4006381333931"),  # JSON-LD sometimes gives a number
        ("036000291452", "036000291452"),  # UPC-A kept as is
        ("96385074", "96385074"),  # EAN-8
        ("4006381333932", None),  # bad check digit
        ("12345", None),
        ("ABC", None),
        ("", None),
        (None, None),
    ],
)
def test_ean_normalization(raw: object, expected: str | None) -> None:
    assert normalize_gtin(raw) == expected
    assert make(ean=raw).ean == expected


def test_gtin_check_digit() -> None:
    assert gtin_is_valid("00012345600012")  # GTIN-14
    assert not gtin_is_valid("00012345600013")


def test_old_price_not_higher_than_price_is_dropped() -> None:
    assert make(old_price_bani=8999).old_price_bani is None
    assert make(old_price_bani=5000).old_price_bani is None


@pytest.mark.parametrize(
    "bad",
    [
        {"price_bani": -1},
        {"old_price_bani": -1},
        {"price_bani": 89.99},  # floats are rejected: prices must be integer bani
        {"url": "/relative/path"},
        {"url": "ftp://x.ro/p"},
        {"image_url": "//cdn.example/x.jpg"},
        {"title": "   "},
        {"retailer": ""},
        {"currency": "lei"},
        {"size_value": "0", "size_unit": "ml"},
        {"size_value": "30", "size_unit": "oz"},
        {"size_value": "30"},  # unit missing
        {"size_unit": "ml"},  # value missing
        {"unexpected_field": 1},
    ],
)
def test_invalid(bad: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        make(**bad)


def test_empty_brand_becomes_none() -> None:
    assert make(brand="  ").brand is None


def test_scraped_at_converted_to_utc() -> None:
    bucharest = timezone(timedelta(hours=3))
    offer = make(scraped_at=datetime(2026, 9, 25, 12, 0, tzinfo=bucharest))
    assert offer.scraped_at == datetime(2026, 9, 25, 9, 0, tzinfo=UTC)
    assert make(scraped_at=datetime(2026, 9, 25, 9, 0)).scraped_at.tzinfo == UTC


def test_frozen() -> None:
    offer = make()
    with pytest.raises(ValidationError):
        offer.price_bani = 1  # type: ignore[misc]


def test_to_snapshot_roundtrip_through_upsert(session: Session) -> None:
    retailer = Retailer(slug="notino", name="Notino", domain="notino.ro")
    session.add(retailer)
    offer = make(brand="La Roche-Posay", ean="3337875598996", size_value="40", size_unit="ml")
    result = upsert_offer(session, retailer, offer.to_snapshot(), offer.scraped_at)
    assert result.outcome is UpsertOutcome.CREATED
    stored = result.offer
    assert (stored.url, stored.title, stored.brand_name) == (
        offer.url,
        offer.title,
        "La Roche-Posay",
    )
    assert (stored.ean, stored.size_value, stored.size_unit) == ("3337875598996", Decimal(40), "ml")
