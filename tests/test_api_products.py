from typing import Any

import pytest
from fastapi.testclient import TestClient


def ids(body: dict[str, Any]) -> list[int]:
    return [p["id"] for p in body["items"]]


def test_healthz(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_list_all(client: TestClient) -> None:
    body = client.get("/api/products").json()
    assert body["total"] == 5
    assert ids(body) == [1, 2, 3, 4, 5]


@pytest.mark.parametrize(
    ("q", "expected"),
    [
        ("effaclar", [1]),  # name, case-insensitive
        ("la roche-posay", [1, 2]),  # brand
        ("  CICAPLAST   baume ", [2]),  # whitespace collapsed
        ("cleanser", [3]),  # name only; category is not searched
        ("no such product", []),
    ],
)
def test_search_q(client: TestClient, q: str, expected: list[int]) -> None:
    body = client.get("/api/products", params={"q": q}).json()
    assert ids(body) == expected
    assert body["total"] == len(expected)


def test_filter_brand_is_exact_match(client: TestClient) -> None:
    body = client.get("/api/products", params={"brand": "la roche-posay"}).json()
    assert ids(body) == [1, 2]
    # Partial brand names do not match the brand filter.
    assert client.get("/api/products", params={"brand": "roche"}).json()["total"] == 0


def test_filter_category(client: TestClient) -> None:
    body = client.get("/api/products", params={"category": "SERUM"}).json()
    assert ids(body) == [1, 4]


def test_filters_combine(client: TestClient) -> None:
    params = {"q": "cleanser", "category": "cleanser", "brand": "CeraVe"}
    body = client.get("/api/products", params=params).json()
    assert ids(body) == [3]


def test_pagination(client: TestClient) -> None:
    first = client.get("/api/products", params={"limit": 2, "offset": 0}).json()
    second = client.get("/api/products", params={"limit": 2, "offset": 2}).json()
    last = client.get("/api/products", params={"limit": 2, "offset": 4}).json()
    assert (ids(first), ids(second), ids(last)) == ([1, 2], [3, 4], [5])
    # total counts all matches, not just the page
    assert first["total"] == second["total"] == last["total"] == 5


def test_pagination_past_end(client: TestClient) -> None:
    body = client.get("/api/products", params={"offset": 50}).json()
    assert body == {"total": 5, "items": []}


def test_pagination_applies_after_filtering(client: TestClient) -> None:
    body = client.get("/api/products", params={"category": "serum", "limit": 1, "offset": 1}).json()
    assert body["total"] == 2
    assert ids(body) == [4]


@pytest.mark.parametrize(
    "params",
    [{"limit": 0}, {"limit": -1}, {"limit": 101}, {"offset": -1}, {"limit": "abc"}],
)
def test_invalid_pagination_rejected(client: TestClient, params: dict[str, Any]) -> None:
    assert client.get("/api/products", params=params).status_code == 422


def test_bundled_sample_data_is_served() -> None:
    """Smoke test against the real bundled JSON (no monkeypatching)."""
    from beautycrawler.api.main import app

    with TestClient(app) as c:
        body = c.get("/api/products").json()
    assert body["total"] >= 1
