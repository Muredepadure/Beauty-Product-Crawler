from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from beautycrawler.api.main import app
from beautycrawler.api.routers import products
from beautycrawler.config import Settings
from beautycrawler.db import Base
from beautycrawler.db.session import make_engine, make_session_factory

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


@pytest.fixture
def engine() -> Iterator[Engine]:
    """Fresh in-memory SQLite database with all tables (FKs enforced)."""
    eng = make_engine("sqlite://")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with make_session_factory(engine)() as s:
        yield s


UA = "BeautyCrawlerTest/1.0 (+https://example.org/bot)"


class FakeTime:
    """Monotonic clock that only advances when the fetcher sleeps."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(round(seconds, 6))
        self.now += seconds


@pytest.fixture
def settings() -> Settings:
    """Crawler settings for fetcher/spider tests (independent of env and .env)."""
    return Settings(
        user_agent=UA,
        request_delay_seconds=2.0,
        max_retries=2,
        retry_backoff_seconds=1.0,
        robots_cache_ttl_seconds=3600,
        _env_file=None,
    )


@pytest.fixture
def fake_time() -> FakeTime:
    return FakeTime()
