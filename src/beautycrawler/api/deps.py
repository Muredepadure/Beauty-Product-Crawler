"""FastAPI dependencies: one engine per process, one session per request.

Tests replace `get_session` via `app.dependency_overrides`.
"""

from collections.abc import Iterator
from functools import cache

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from beautycrawler.db.session import make_engine, make_session_factory


@cache
def get_engine() -> Engine:
    return make_engine()


def get_session() -> Iterator[Session]:
    with make_session_factory(get_engine())() as session:
        yield session
