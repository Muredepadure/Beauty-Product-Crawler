"""P5.5: seller view `GET /api/compare?brand=X`."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from beautycrawler.api.routers.compare import pct_diff
from beautycrawler.db.models import Brand, Offer, Product, Retailer


@pytest.fixture
def market(api_session: Session) -> dict[str, int]:
    """La Roche-Posay on three retailers (prices in bani):

    Effaclar Duo+: notino 100.00, emag 80.00 + 90.00 (two sellers), drmax 70.00 out of stock
    Cicaplast:     notino 50.00 only
    Toleriane:     no offers (not compared)
    """
    s = api_session
    notino = Retailer(slug="notino", name="Notino", domain="notino.ro")
    emag = Retailer(slug="emag", name="eMAG", domain="emag.ro")
    drmax = Retailer(slug="drmax", name="Dr.Max", domain="drmax.ro")
    lrp = Brand(name="La Roche-Posay", normalized_name="la roche posay")
    other = Brand(name="CeraVe", normalized_name="cerave")
    duo = Product(brand=lrp, name="Effaclar Duo+", normalized_name="effaclar duo+")
    cica = Product(brand=lrp, name="Cicaplast", normalized_name="cicaplast")
    toler = Product(brand=lrp, name="Toleriane", normalized_name="toleriane")
    cerave = Product(brand=other, name="Cleanser", normalized_name="cleanser")
    s.add(toler)  # no offers; everything else is added through its offers
    n = iter(range(100))

    def offer(p: Product, r: Retailer, price: int, in_stock: bool = True) -> None:
        s.add(
            Offer(
                product=p,
                retailer=r,
                url=f"https://{r.domain}/{next(n)}",
                title=p.name,
                price_bani=price,
                in_stock=in_stock,
            )
        )

    offer(duo, notino, 10_000)
    offer(duo, emag, 9_000)
    offer(duo, emag, 8_000)
    offer(duo, drmax, 7_000, in_stock=False)
    offer(cica, notino, 5_000)
    offer(cerave, notino, 1_000)
    s.commit()
    return {"duo": duo.id, "cica": cica.id}


def prices(product: dict[str, Any]) -> list[tuple[str, int, bool, float | None, float | None]]:
    return [
        (
            p["retailer"]["slug"],
            p["price_bani"],
            p["in_stock"],
            p["vs_min_pct"],
            p["vs_median_pct"],
        )
        for p in product["prices"]
    ]


def test_compare_brand(client: TestClient, market: dict[str, int]) -> None:
    body = client.get("/api/compare", params={"brand": "LRP"}).json()
    assert body["brand"] == "La Roche-Posay"
    assert (body["total"], body["page"], body["page_size"]) == (2, 1, 50)
    cica, duo = body["products"]  # by name; Toleriane has no offers
    assert (cica["product_id"], duo["product_id"]) == (market["cica"], market["duo"])

    # market = emag's cheapest seller (80) + notino (100); drmax is out of stock
    assert (duo["market_min_bani"], duo["market_median_bani"]) == (8_000, 9_000)
    assert prices(duo) == [
        ("emag", 8_000, True, 0.0, -11.1),
        ("notino", 10_000, True, 25.0, 11.1),
        ("drmax", 7_000, False, -12.5, -22.2),
    ]
    assert [p["is_cheapest"] for p in duo["prices"]] == [True, False, False]

    assert (cica["market_min_bani"], cica["market_median_bani"]) == (5_000, 5_000)
    assert prices(cica) == [("notino", 5_000, True, 0.0, 0.0)]


def test_compare_retailer_positions(client: TestClient, market: dict[str, int]) -> None:
    body = client.get("/api/compare", params={"brand": "la roche-posay"}).json()
    positions = {
        p["retailer"]["slug"]: (p["products_listed"], p["cheapest_count"], p["avg_vs_median_pct"])
        for p in body["retailers"]
    }
    assert positions == {
        "drmax": (1, 0, None),  # only out of stock: no in-stock comparison
        "emag": (1, 1, -11.1),
        "notino": (2, 1, 5.5),  # mean of +11.1 and 0.0, rounded
    }
    assert [p["retailer"]["slug"] for p in body["retailers"]] == ["drmax", "emag", "notino"]


def test_compare_pagination_keeps_positions_global(
    client: TestClient, market: dict[str, int]
) -> None:
    body = client.get("/api/compare", params={"brand": "LRP", "page": 2, "page_size": 1}).json()
    assert [p["product_id"] for p in body["products"]] == [market["duo"]]
    assert body["total"] == 2
    notino = next(p for p in body["retailers"] if p["retailer"]["slug"] == "notino")
    assert notino["products_listed"] == 2


def test_compare_product_with_nothing_in_stock(
    client: TestClient, api_session: Session, market: dict[str, int]
) -> None:
    for offer in api_session.query(Offer).filter(Offer.product_id == market["cica"]):
        offer.in_stock = False
    api_session.commit()
    cica = client.get("/api/compare", params={"brand": "LRP"}).json()["products"][0]
    assert (cica["market_min_bani"], cica["market_median_bani"]) == (None, None)
    assert prices(cica) == [("notino", 5_000, False, None, None)]


def test_compare_brand_without_offers(client: TestClient, api_session: Session) -> None:
    api_session.add(Brand(name="Nuxe", normalized_name="nuxe"))
    api_session.commit()
    body = client.get("/api/compare", params={"brand": "nuxe"}).json()
    assert (body["products"], body["retailers"], body["total"]) == ([], [], 0)


@pytest.mark.parametrize(
    ("params", "status"),
    [
        ({"brand": "Unknown"}, 404),
        ({}, 422),
        ({"brand": ""}, 422),
        ({"brand": "x", "page": 0}, 422),
    ],
)
def test_compare_errors(
    client: TestClient, market: dict[str, int], params: dict[str, Any], status: int
) -> None:
    assert client.get("/api/compare", params=params).status_code == status


def test_pct_diff() -> None:
    assert pct_diff(12_000, 10_000) == 20.0
    assert pct_diff(9_000, 10_000) == -10.0
    assert pct_diff(10_000, 3) == pytest.approx(333233.3)
    assert pct_diff(100, None) is None
    assert pct_diff(100, 0) is None
