"""P5.4: `GET /api/retailers` and `GET /api/brands`."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from beautycrawler.db.models import Brand, Offer, Product, Retailer


@pytest.fixture
def data(api_session: Session) -> None:
    s = api_session
    notino = Retailer(slug="notino", name="Notino", domain="notino.ro")
    emag = Retailer(slug="emag", name="eMAG", domain="emag.ro")
    dm = Retailer(slug="dm", name="dm drogerie markt", domain="dm.ro", is_active=False)
    lrp = Brand(name="La Roche-Posay", normalized_name="la roche posay")
    loreal = Brand(name="L'Oréal Paris", normalized_name="loreal paris")
    lorealpro = Brand(name="L'Oréal Professionnel", normalized_name="loreal professionnel")
    s.add(Brand(name="Avène", normalized_name="avene"))  # no products
    duo = Product(brand=lrp, name="Effaclar Duo+", normalized_name="effaclar duo+")
    cica = Product(brand=lrp, name="Cicaplast", normalized_name="cicaplast")
    serum = Product(brand=loreal, name="Revitalift", normalized_name="revitalift")
    s.add_all([notino, emag, dm, lorealpro, duo, cica, serum])

    def offer(retailer: Retailer, product: Product | None, n: int) -> None:
        s.add(
            Offer(
                retailer=retailer,
                product=product,
                url=f"https://{retailer.domain}/{n}",
                title="x",
                price_bani=1_000,
                in_stock=True,
            )
        )

    offer(notino, duo, 1)
    offer(notino, cica, 2)
    offer(notino, None, 3)  # not matched yet: counts as an offer, not a product
    offer(emag, duo, 4)
    offer(emag, duo, 5)  # second marketplace seller of the same product
    s.commit()


def test_retailers(client: TestClient, data: None) -> None:
    body = client.get("/api/retailers").json()
    assert body == [
        {
            "slug": "dm",
            "name": "dm drogerie markt",
            "domain": "dm.ro",
            "is_active": False,
            "offer_count": 0,
            "product_count": 0,
        },
        {
            "slug": "emag",
            "name": "eMAG",
            "domain": "emag.ro",
            "is_active": True,
            "offer_count": 2,
            "product_count": 1,
        },
        {
            "slug": "notino",
            "name": "Notino",
            "domain": "notino.ro",
            "is_active": True,
            "offer_count": 3,
            "product_count": 2,
        },
    ]


@pytest.mark.parametrize(("active", "slugs"), [("true", ["emag", "notino"]), ("false", ["dm"])])
def test_retailers_active_filter(
    client: TestClient, data: None, active: str, slugs: list[str]
) -> None:
    body = client.get("/api/retailers", params={"active": active}).json()
    assert [r["slug"] for r in body] == slugs


def test_retailers_empty(client: TestClient) -> None:
    assert client.get("/api/retailers").json() == []


def names(body: dict[str, Any]) -> list[str]:
    return [b["name"] for b in body["items"]]


def test_brands(client: TestClient, data: None) -> None:
    body = client.get("/api/brands").json()
    assert (body["total"], body["page"], body["page_size"]) == (4, 1, 50)
    assert [(b["name"], b["product_count"]) for b in body["items"]] == [
        ("Avène", 0),
        ("La Roche-Posay", 2),
        ("L'Oréal Paris", 1),
        ("L'Oréal Professionnel", 0),
    ]


@pytest.mark.parametrize(
    ("q", "expected"),
    [
        ("l'oréal", ["L'Oréal Paris", "L'Oréal Professionnel"]),
        ("LOREAL prof", ["L'Oréal Professionnel"]),
        ("avene", ["Avène"]),
        ("roche-posay", ["La Roche-Posay"]),
        ("nivea", []),
    ],
)
def test_brands_search(client: TestClient, data: None, q: str, expected: list[str]) -> None:
    body = client.get("/api/brands", params={"q": q}).json()
    assert names(body) == expected
    assert body["total"] == len(expected)


def test_brands_pagination(client: TestClient, data: None) -> None:
    p1 = client.get("/api/brands", params={"page_size": 3}).json()
    p2 = client.get("/api/brands", params={"page_size": 3, "page": 2}).json()
    assert (len(p1["items"]), len(p2["items"]), p2["total"]) == (3, 1, 4)
    assert names(p2) == ["L'Oréal Professionnel"]


@pytest.mark.parametrize("params", [{"page": 0}, {"page_size": 0}, {"page_size": 201}])
def test_brands_invalid_params(client: TestClient, params: dict[str, Any]) -> None:
    assert client.get("/api/brands", params=params).status_code == 422


def test_openapi_documents_all_endpoints(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    assert {
        "/api/products",
        "/api/products/{product_id}",
        "/api/products/{product_id}/history",
        "/api/retailers",
        "/api/brands",
    } <= spec["paths"].keys()
    schemas = spec["components"]["schemas"]
    assert {"ProductPage", "ProductDetail", "ProductHistory", "RetailerOut", "BrandPage"} <= (
        schemas.keys()
    )
    # every endpoint's 200 response references a documented schema
    for path, ops in spec["paths"].items():
        if path.startswith("/api/"):
            ok = ops["get"]["responses"]["200"]["content"]["application/json"]["schema"]
            assert ok, path
