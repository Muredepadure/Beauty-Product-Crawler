from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from beautycrawler.config import get_settings


def _enable_sqlite_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def make_engine(url: str | None = None, **kwargs: Any) -> Engine:
    """Create an engine for `url` (default: settings.database_url).

    SQLite does not enforce foreign keys (and so ON DELETE rules) unless asked per
    connection; this turns that on so SQLite behaves like Postgres.
    """
    engine = create_engine(url or get_settings().database_url, **kwargs)
    if engine.dialect.name == "sqlite":
        event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
