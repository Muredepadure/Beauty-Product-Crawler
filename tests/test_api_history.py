"""P5.3: `GET /api/products/{id}/history` (history built through the real write path)."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from beautycrawler.db.models import Product, Retailer
from beautycrawler.db.repository import OfferSnapshot, upsert_offer

NOW = datetime.now(UTC).replace(microsecond=0)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


@pytest.fixture
def product_id(api_session: Session) -> int:
    s = api_session
    notino = Retailer(slug="notino", name="Notino", domain="notino.ro")
    emag = Retailer(slug="emag", name="eMAG", domain="emag.ro")
    product = Product(name="Effaclar Duo+", normalized_name="effaclar duo+")
    s.add_all([notino, emag, product])
    s.flush()

    def observe(
        retailer: Retailer,
        url: str,
        days_ago: int,
        price: int,
        *,
        in_stock: bool,
        old_price_bani: int | None = None,
        seller_name: str | None = None,
    ) -> None:
        snap = OfferSnapshot(
            url=url,
            title="Effaclar Duo+",
            price_bani=price,
            in_stock=in_stock,
            old_price_bani=old_price_bani,
            seller_name=seller_name,
        )
        result = upsert_offer(s, retailer, snap, NOW - timedelta(days=days_ago))
        result.offer.product = product

    # notino: 89.90 -> sale 74.50 -> out of stock; unchanged crawls add no points
    observe(notino, "https://notino.ro/duo", 60, 8_990, in_stock=True)
    observe(notino, "https://notino.ro/duo", 50, 8_990, in_stock=True)
    observe(notino, "https://notino.ro/duo", 20, 7_450, in_stock=True, old_price_bani=8_990)
    observe(notino, "https://notino.ro/duo", 5, 7_450, in_stock=False, old_price_bani=8_990)
    observe(notino, "https://notino.ro/duo", 1, 7_450, in_stock=False, old_price_bani=8_990)
    # emag marketplace seller, one price
    observe(emag, "https://emag.ro/duo", 3, 8_000, in_stock=True, seller_name="Beauty SRL")
    s.commit()
    return product.id


def test_history_full(client: TestClient, product_id: int) -> None:
    body = client.get(f"/api/products/{product_id}/history").json()
    assert body["product_id"] == product_id
    emag, notino = body["series"]  # by retailer slug
    assert (emag["retailer"]["slug"], notino["retailer"]["slug"]) == ("emag", "notino")
    assert emag["seller_name"] == "Beauty SRL"
    assert [
        (p["scraped_at"], p["price_bani"], p["old_price_bani"], p["in_stock"])
        for p in notino["points"]
    ] == [
        (_iso(NOW - timedelta(days=60)), 8_990, None, True),
        (_iso(NOW - timedelta(days=20)), 7_450, 8_990, True),
        (_iso(NOW - timedelta(days=5)), 7_450, 8_990, False),
    ]
    assert notino["last_seen_at"] == _iso(NOW - timedelta(days=1))
    assert notino["url"] == "https://notino.ro/duo"
    assert [p["price_bani"] for p in emag["points"]] == [8_000]


def test_history_window_keeps_price_in_effect_at_start(client: TestClient, product_id: int) -> None:
    body = client.get(f"/api/products/{product_id}/history", params={"days": 10}).json()
    emag, notino = body["series"]
    # the 20-days-ago sale price was still in effect 10 days ago, so it's included
    assert [(p["price_bani"], p["in_stock"]) for p in notino["points"]] == [
        (7_450, True),
        (7_450, False),
    ]
    assert len(emag["points"]) == 1


def test_history_window_before_everything(client: TestClient, product_id: int) -> None:
    body = client.get(f"/api/products/{product_id}/history", params={"days": 365}).json()
    assert [len(s["points"]) for s in body["series"]] == [1, 3]


def test_history_of_product_without_offers(client: TestClient, api_session: Session) -> None:
    product = Product(name="Nou", normalized_name="nou")
    api_session.add(product)
    api_session.commit()
    body = client.get(f"/api/products/{product.id}/history").json()
    assert body == {"product_id": product.id, "series": []}


@pytest.mark.parametrize(
    ("url", "status"),
    [
        ("/api/products/999/history", 404),
        ("/api/products/0/history", 422),
        ("/api/products/1/history?days=0", 422),
        ("/api/products/1/history?days=5000", 422),
    ],
)
def test_history_errors(client: TestClient, url: str, status: int) -> None:
    assert client.get(url).status_code == status
