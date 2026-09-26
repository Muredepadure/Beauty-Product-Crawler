"""P6.4: price-drop detection (query + `GET /api/price-drops`)."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from beautycrawler.db.models import Brand, Offer, Product, Retailer
from beautycrawler.db.price_drops import find_price_drops
from beautycrawler.db.repository import OfferSnapshot, upsert_offer

NOW = datetime.now(UTC).replace(microsecond=0)
SNAP = OfferSnapshot(
    url="https://notino.ro/x", title="Effaclar Duo+", price_bani=10_000, in_stock=True
)


def _prices(
    session: Session, retailer: Retailer, url: str, steps: list[tuple[int, int, bool]]
) -> None:
    """steps: (hours ago, price, in stock), oldest first, through the real write path."""
    for hours_ago, price, in_stock in steps:
        snap = replace(SNAP, url=url, price_bani=price, in_stock=in_stock)
        upsert_offer(session, retailer, snap, NOW - timedelta(hours=hours_ago))


@pytest.fixture
def notino(session: Session) -> Retailer:
    r = Retailer(slug="notino", name="Notino", domain="notino.ro")
    session.add(r)
    session.flush()
    return r


def _drops(
    session: Session, min_pct: float = 10, hours: int = 24
) -> list[tuple[str, int, int, float]]:
    since = NOW - timedelta(hours=hours)
    return [
        (d.offer.url, d.previous_price_bani, d.price_bani, d.drop_pct)
        for d in find_price_drops(session, min_pct=min_pct, since=since)
    ]


def test_recent_big_drop_is_found(session: Session, notino: Retailer) -> None:
    _prices(session, notino, "https://n/a", [(72, 10_000, True), (2, 7_500, True)])
    assert _drops(session) == [("https://n/a", 10_000, 7_500, 25.0)]


def test_threshold_is_inclusive(session: Session, notino: Retailer) -> None:
    _prices(session, notino, "https://n/a", [(72, 10_000, True), (2, 9_000, True)])
    assert _drops(session, min_pct=10) == [("https://n/a", 10_000, 9_000, 10.0)]
    assert _drops(session, min_pct=10.1) == []


@pytest.mark.parametrize(
    "steps",
    [
        [(72, 10_000, True), (2, 12_000, True)],  # price went up
        [(72, 10_000, True)],  # a single observation: nothing to compare
        [(72, 10_000, True), (30, 7_000, True)],  # dropped, but before the window
        [(72, 10_000, True), (2, 7_000, False)],  # cheaper, but not buyable
        [(72, 10_000, True), (5, 7_000, True), (2, 7_000, False)],  # sold out since
    ],
)
def test_not_a_current_drop(
    session: Session, notino: Retailer, steps: list[tuple[int, int, bool]]
) -> None:
    _prices(session, notino, "https://n/a", steps)
    assert _drops(session) == []


def test_only_latest_change_counts(session: Session, notino: Retailer) -> None:
    # dropped 30 %, then partially recovered: the latest change is a rise
    _prices(
        session, notino, "https://n/a", [(10, 10_000, True), (6, 7_000, True), (2, 8_000, True)]
    )
    assert _drops(session) == []


def test_restock_at_a_lower_price(session: Session, notino: Retailer) -> None:
    _prices(session, notino, "https://n/a", [(72, 10_000, False), (2, 8_000, True)])
    assert _drops(session) == [("https://n/a", 10_000, 8_000, 20.0)]


def test_biggest_drops_first_and_limit(session: Session, notino: Retailer) -> None:
    _prices(session, notino, "https://n/a", [(72, 10_000, True), (2, 8_000, True)])  # 20 %
    _prices(session, notino, "https://n/b", [(72, 5_000, True), (3, 2_500, True)])  # 50 %
    _prices(session, notino, "https://n/c", [(72, 1_000, True), (1, 850, True)])  # 15 %
    assert [url for url, *_ in _drops(session)] == ["https://n/b", "https://n/a", "https://n/c"]
    since = NOW - timedelta(hours=24)
    assert len(find_price_drops(session, min_pct=10, since=since, limit=2)) == 2


# --- endpoint ----------------------------------------------------------------------


def test_price_drops_endpoint(client: TestClient, api_session: Session) -> None:
    s = api_session
    notino = Retailer(slug="notino", name="Notino", domain="notino.ro")
    emag = Retailer(slug="emag", name="eMAG", domain="emag.ro")
    s.add_all([notino, emag])
    s.flush()
    _prices(s, notino, "https://notino.ro/duo", [(48, 8_990, True), (3, 6_290, True)])
    _prices(s, emag, "https://emag.ro/cica", [(48, 5_000, True), (5, 4_600, True)])  # 8 %
    product = Product(
        brand=Brand(name="La Roche-Posay", normalized_name="la roche posay"),
        name="Effaclar Duo+",
        normalized_name="effaclar duo+",
    )
    s.query(Offer).filter_by(url="https://notino.ro/duo").one().product = product
    s.commit()

    body = client.get("/api/price-drops").json()
    assert body["min_pct"] == 10.0
    assert body["since"].endswith("Z")
    [item] = body["items"]
    assert item["product"] == {"id": product.id, "name": "Effaclar Duo+", "brand": "La Roche-Posay"}
    assert item["retailer"] == {"slug": "notino", "name": "Notino"}
    assert (item["previous_price_bani"], item["price_bani"], item["drop_pct"]) == (
        8_990,
        6_290,
        30.0,
    )
    assert item["url"] == "https://notino.ro/duo"
    assert item["changed_at"] == (NOW - timedelta(hours=3)).isoformat().replace("+00:00", "Z")

    lower = client.get("/api/price-drops", params={"min_pct": 5}).json()["items"]
    assert [(i["retailer"]["slug"], i["product"]) for i in lower][1] == ("emag", None)
    assert client.get("/api/price-drops", params={"hours": 2}).json()["items"] == []


@pytest.mark.parametrize(
    "params",
    [{"min_pct": 0}, {"min_pct": 101}, {"hours": 0}, {"hours": 5000}, {"limit": 0}, {"limit": 201}],
)
def test_price_drops_invalid_params(client: TestClient, params: dict[str, float]) -> None:
    assert client.get("/api/price-drops", params=params).status_code == 422
