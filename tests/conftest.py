from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from beautycrawler.api.deps import get_session
from beautycrawler.api.main import app
from beautycrawler.config import Settings
from beautycrawler.db import Base
from beautycrawler.db.session import make_engine, make_session_factory


@pytest.fixture
def api_engine() -> Iterator[Engine]:
    """In-memory SQLite shared across threads (TestClient serves from another thread)."""
    eng = make_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def api_session(api_engine: Engine) -> Iterator[Session]:
    """Session on the API's database, for arranging test data (commit before requests)."""
    with make_session_factory(api_engine)() as s:
        yield s


@pytest.fixture
def client(api_engine: Engine) -> Iterator[TestClient]:
    """API client backed by `api_engine`."""
    factory = make_session_factory(api_engine)

    def session_override() -> Iterator[Session]:
        with factory() as s:
            yield s

    app.dependency_overrides[get_session] = session_override
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_session, None)


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
