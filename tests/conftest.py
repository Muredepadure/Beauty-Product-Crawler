from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from beautycrawler.api.main import app
from beautycrawler.api.routers import products

SAMPLE_PRODUCTS: list[dict[str, Any]] = [
    {"id": 1, "name": "Effaclar Duo+ 40ml", "brand": "La Roche-Posay", "category": "Serum"},
    {"id": 2, "name": "Cicaplast Baume B5", "brand": "La Roche-Posay", "category": "Balsam"},
    {"id": 3, "name": "Hydrating Cleanser", "brand": "CeraVe", "category": "Cleanser"},
    {"id": 4, "name": "Niacinamide 10% + Zinc", "brand": "The Ordinary", "category": "Serum"},
    {"id": 5, "name": "Sensibio H2O", "brand": "Bioderma", "category": "Cleanser"},
]


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """API client backed by a fixed product list, independent of the bundled sample data."""
    monkeypatch.setattr(products, "PRODUCTS", SAMPLE_PRODUCTS)
    with TestClient(app) as c:
        yield c
