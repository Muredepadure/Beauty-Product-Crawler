"""P5.1: DB-backed `GET /api/products` (search, filters, sort, pagination)."""

from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from beautycrawler.api.routers.products import search_words
from beautycrawler.db.models import Brand, Offer, Product, Retailer
from beautycrawler.normalization.text import fold


def ids(body: dict[str, Any]) -> list[int]:
    return [p["id"] for p in body["items"]]


@pytest.fixture
def catalogue(api_session: Session) -> dict[str, int]:
    """Five products; offers (prices in bani) on three retailers."""
    s = api_session
    notino, emag, drmax = (
        Retailer(slug=slug, name=slug, domain=f"{slug}.ro") for slug in ("notino", "emag", "drmax")
    )
    lrp = Brand(name="La Roche-Posay", normalized_name="la roche posay")
    cerave = Brand(name="CeraVe", normalized_name="cerave")
    loreal = Brand(name="L'Oréal Paris", normalized_name="loreal paris")

    def product(brand: Brand | None, name: str, category: str | None) -> Product:
        p = Product(
            brand=brand,
            name=name,
            normalized_name=fold(name),
            category=category,
            size_value=Decimal(40),
            size_unit="ml",
        )
        s.add(p)
        return p

    duo = product(lrp, "Effaclar Duo+ cremă corectoare", "Îngrijirea tenului")
    cica = product(lrp, "Cicaplast Baume B5+", "Îngrijirea tenului")
    cleanser = product(cerave, "Hydrating Cleanser", "Curățare")
    revita = product(loreal, "Revitalift Filler ser", "Seruri")
    nobrand = product(None, "Apă micelară", None)

    def offer(p: Product, retailer: Retailer, price: int, in_stock: bool = True) -> None:
        s.add(
            Offer(
                product=p,
                retailer=retailer,
                url=f"https://{retailer.domain}/{price}",
                title=p.name,
                price_bani=price,
                in_stock=in_stock,
            )
        )

    offer(duo, notino, 8_990)
    offer(duo, emag, 7_450)
    offer(duo, drmax, 6_000, in_stock=False)  # cheapest but unavailable
    offer(cica, notino, 5_500)
    offer(revita, emag, 12_000)
    offer(revita, drmax, 9_900)
    offer(cleanser, emag, 4_000, in_stock=False)
    s.commit()
    return {
        "duo": duo.id,
        "cica": cica.id,
        "cleanser": cleanser.id,
        "revita": revita.id,
        "nobrand": nobrand.id,
    }


def test_healthz(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_empty_database(client: TestClient) -> None:
    assert client.get("/api/products").json() == {
        "total": 0,
        "page": 1,
        "page_size": 24,
        "items": [],
    }


def test_list_all_sorted_by_name(client: TestClient, catalogue: dict[str, int]) -> None:
    body = client.get("/api/products").json()
    assert body["total"] == 5
    c = catalogue
    # "Apă" folds to "apa", so it sorts first
    assert ids(body) == [c["nobrand"], c["cica"], c["duo"], c["cleanser"], c["revita"]]


def test_item_shape_and_offer_stats(client: TestClient, catalogue: dict[str, int]) -> None:
    items = {p["id"]: p for p in client.get("/api/products").json()["items"]}
    duo = items[catalogue["duo"]]
    assert duo == {
        "id": catalogue["duo"],
        "name": "Effaclar Duo+ cremă corectoare",
        "brand": "La Roche-Posay",
        "category": "Îngrijirea tenului",
        "size_value": "40.000",
        "size_unit": "ml",
        "ean": None,
        "image_url": None,
        "lowest_price_bani": 7_450,  # the out-of-stock 60 lei offer doesn't count
        "currency": "RON",
        "offer_count": 3,
        "retailer_count": 3,
        "in_stock": True,
    }
    cleanser = items[catalogue["cleanser"]]
    assert (cleanser["lowest_price_bani"], cleanser["in_stock"]) == (None, False)
    nobrand = items[catalogue["nobrand"]]
    assert (nobrand["brand"], nobrand["offer_count"], nobrand["in_stock"]) == (None, 0, False)


@pytest.mark.parametrize(
    ("q", "expected"),
    [
        ("effaclar", ["duo"]),
        ("EFFACLAR   duo", ["duo"]),  # case and whitespace
        ("crema", ["duo"]),  # query without diacritics finds "cremă"
        ("cremă", ["duo"]),
        ("apa micelara", ["nobrand"]),
        ("la roche-posay", ["cica", "duo"]),  # brand words
        ("roche effaclar", ["duo"]),  # brand + name words combined
        ("L'Oréal ser", ["revita"]),
        ("b5+", ["cica"]),
        ("effaclar cleanser", []),  # every word must match
        ("no such product", []),
    ],
)
def test_search_q(
    client: TestClient, catalogue: dict[str, int], q: str, expected: list[str]
) -> None:
    body = client.get("/api/products", params={"q": q}).json()
    assert ids(body) == [catalogue[k] for k in expected]
    assert body["total"] == len(expected)


def test_search_punctuation_only_matches_everything(
    client: TestClient, catalogue: dict[str, int]
) -> None:
    assert client.get("/api/products", params={"q": " - "}).json()["total"] == 5


def test_search_words() -> None:
    assert search_words("  L’Oréal  Duo+ duo ") == ["loreal", "duo"]
    assert search_words("Îngrijire ȚESĂTURĂ ţesătură") == ["ingrijire", "tesatura"]


@pytest.mark.parametrize("brand", ["La Roche-Posay", "la roche posay", "LRP", "LA ROCHE-POSAY®"])
def test_filter_brand_accepts_aliases(
    client: TestClient, catalogue: dict[str, int], brand: str
) -> None:
    body = client.get("/api/products", params={"brand": brand}).json()
    assert ids(body) == [catalogue["cica"], catalogue["duo"]]


def test_filter_brand_is_exact(client: TestClient, catalogue: dict[str, int]) -> None:
    assert client.get("/api/products", params={"brand": "roche"}).json()["total"] == 0


@pytest.mark.parametrize("category", ["Îngrijirea tenului", "ingrijirea TENULUI"])
def test_filter_category_ignores_case_and_diacritics(
    client: TestClient, catalogue: dict[str, int], category: str
) -> None:
    body = client.get("/api/products", params={"category": category}).json()
    assert ids(body) == [catalogue["cica"], catalogue["duo"]]


def test_filter_unknown_category(client: TestClient, catalogue: dict[str, int]) -> None:
    assert client.get("/api/products", params={"category": "Parfum"}).json()["total"] == 0


def test_filters_combine(client: TestClient, catalogue: dict[str, int]) -> None:
    params = {"q": "crema", "brand": "LRP", "category": "ingrijirea tenului"}
    assert ids(client.get("/api/products", params=params).json()) == [catalogue["duo"]]


@pytest.mark.parametrize(
    ("sort", "expected"),
    [
        # unpriced (no in-stock offer) products always last, by id
        ("price_asc", ["cica", "duo", "revita", "cleanser", "nobrand"]),
        ("price_desc", ["revita", "duo", "cica", "cleanser", "nobrand"]),
        ("retailers", ["duo", "revita", "cica", "cleanser", "nobrand"]),
    ],
)
def test_sort(
    client: TestClient, catalogue: dict[str, int], sort: str, expected: list[str]
) -> None:
    body = client.get("/api/products", params={"sort": sort}).json()
    assert ids(body) == [catalogue[k] for k in expected]


def test_pagination(client: TestClient, catalogue: dict[str, int]) -> None:
    pages = [
        client.get("/api/products", params={"page": n, "page_size": 2}).json() for n in (1, 2, 3)
    ]
    assert [len(p["items"]) for p in pages] == [2, 2, 1]
    assert all(p["total"] == 5 and p["page_size"] == 2 for p in pages)
    assert [p["page"] for p in pages] == [1, 2, 3]
    all_ids = [i for p in pages for i in ids(p)]
    assert all_ids == ids(client.get("/api/products").json())


def test_pagination_past_end(client: TestClient, catalogue: dict[str, int]) -> None:
    body = client.get("/api/products", params={"page": 10}).json()
    assert (body["total"], body["items"]) == (5, [])


def test_pagination_applies_after_filtering(client: TestClient, catalogue: dict[str, int]) -> None:
    params = {"brand": "LRP", "page": 2, "page_size": 1}
    body = client.get("/api/products", params=params).json()
    assert body["total"] == 2
    assert ids(body) == [catalogue["duo"]]


@pytest.mark.parametrize(
    "params",
    [
        {"page": 0},
        {"page": -1},
        {"page_size": 0},
        {"page_size": 101},
        {"page_size": "abc"},
        {"sort": "cheapest"},
    ],
)
def test_invalid_params_rejected(client: TestClient, params: dict[str, Any]) -> None:
    assert client.get("/api/products", params=params).status_code == 422


def test_openapi_documents_response_schema(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    schema = spec["components"]["schemas"]["ProductSummary"]
    assert "lowest_price_bani" in schema["properties"]


# --- P5.2: product detail ----------------------------------------------------------


def test_product_detail_offers_sorted_and_cheapest_flagged(
    client: TestClient, catalogue: dict[str, int]
) -> None:
    body = client.get(f"/api/products/{catalogue['duo']}").json()
    assert body["name"] == "Effaclar Duo+ cremă corectoare"
    assert (body["lowest_price_bani"], body["offer_count"], body["retailer_count"]) == (
        7_450,
        3,
        3,
    )
    offers = body["offers"]
    # in stock by price first; the cheaper out-of-stock offer comes last
    assert [(o["retailer"]["slug"], o["price_bani"], o["in_stock"]) for o in offers] == [
        ("emag", 7_450, True),
        ("notino", 8_990, True),
        ("drmax", 6_000, False),
    ]
    assert [o["is_cheapest"] for o in offers] == [True, False, False]
    first = offers[0]
    assert first["url"] == "https://emag.ro/7450"
    assert first["retailer"] == {"slug": "emag", "name": "emag"}
    assert first["currency"] == "RON"
    assert first["last_seen_at"].endswith("Z")  # UTC, even from SQLite


def test_product_detail_ties_all_flagged(
    client: TestClient, api_session: Session, catalogue: dict[str, int]
) -> None:
    cica = api_session.get(Product, catalogue["cica"])
    emag = api_session.query(Retailer).filter_by(slug="emag").one()
    assert cica is not None
    api_session.add(
        Offer(
            product=cica,
            retailer=emag,
            url="https://emag.ro/cica",
            title="Cicaplast",
            price_bani=5_500,
            in_stock=True,
            old_price_bani=6_500,
        )
    )
    api_session.commit()
    offers = client.get(f"/api/products/{catalogue['cica']}").json()["offers"]
    assert [o["is_cheapest"] for o in offers] == [True, True]
    assert {o["old_price_bani"] for o in offers} == {None, 6_500}


def test_product_detail_without_offers(client: TestClient, catalogue: dict[str, int]) -> None:
    body = client.get(f"/api/products/{catalogue['nobrand']}").json()
    assert (body["offers"], body["lowest_price_bani"], body["in_stock"]) == ([], None, False)


def test_product_detail_nothing_in_stock(client: TestClient, catalogue: dict[str, int]) -> None:
    body = client.get(f"/api/products/{catalogue['cleanser']}").json()
    assert body["lowest_price_bani"] is None
    assert [o["is_cheapest"] for o in body["offers"]] == [False]


def test_product_detail_matches_list_summary(client: TestClient, catalogue: dict[str, int]) -> None:
    listed = {p["id"]: p for p in client.get("/api/products").json()["items"]}
    for product_id in catalogue.values():
        detail = client.get(f"/api/products/{product_id}").json()
        detail.pop("offers")
        assert detail == listed[product_id]


@pytest.mark.parametrize(("path", "status"), [("999", 404), ("0", 422), ("abc", 422)])
def test_product_detail_errors(
    client: TestClient, catalogue: dict[str, int], path: str, status: int
) -> None:
    assert client.get(f"/api/products/{path}").status_code == status


# --- P7.3: price and stock filters -------------------------------------------------


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"in_stock": "true"}, ["cica", "duo", "revita"]),
        ({"in_stock": "false"}, ["nobrand", "cica", "duo", "cleanser", "revita"]),
        ({"max_price": 7_450}, ["cica", "duo"]),  # inclusive; 60 lei out of stock ignored
        ({"min_price": 7_451}, ["revita"]),
        ({"min_price": 5_000, "max_price": 8_000}, ["cica", "duo"]),
        ({"min_price": 100_000}, []),
        ({"max_price": 0}, []),
    ],
)
def test_price_and_stock_filters(
    client: TestClient, catalogue: dict[str, int], params: dict[str, Any], expected: list[str]
) -> None:
    body = client.get("/api/products", params=params).json()
    assert ids(body) == [catalogue[k] for k in expected]
    assert body["total"] == len(expected)


@pytest.mark.parametrize("params", [{"min_price": -1}, {"max_price": "x"}, {"in_stock": "maybe"}])
def test_invalid_price_filters(client: TestClient, params: dict[str, Any]) -> None:
    assert client.get("/api/products", params=params).status_code == 422
