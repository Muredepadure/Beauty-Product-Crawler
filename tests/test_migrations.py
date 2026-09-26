from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from conftest import TEST_DATABASE_URL
from sqlalchemy import inspect, text

from beautycrawler.db import Base
from beautycrawler.db.session import make_engine

REPO_ROOT = Path(__file__).resolve().parents[1]


def alembic_config(url: str) -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["configure_logger"] = False  # don't clobber pytest's logging
    return cfg


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    """A fresh SQLite file, or the (wiped) TEST_DATABASE_URL database when set."""
    if TEST_DATABASE_URL:
        engine = make_engine(TEST_DATABASE_URL)
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
        engine.dispose()
        return TEST_DATABASE_URL
    return f"sqlite:///{tmp_path / 'test.db'}"


def test_upgrade_head_on_fresh_db(db_url: str) -> None:
    command.upgrade(alembic_config(db_url), "head")
    engine = make_engine(db_url)
    tables = set(inspect(engine).get_table_names())
    engine.dispose()
    assert {"retailers", "brands", "products", "offers", "price_history"} <= tables
    assert "alembic_version" in tables


def test_migrations_match_models(db_url: str) -> None:
    """Fails if a model changed without a matching migration."""
    command.upgrade(alembic_config(db_url), "head")
    engine = make_engine(db_url)
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"compare_type": True})
        diff = compare_metadata(ctx, Base.metadata)
    engine.dispose()
    assert diff == []


def test_downgrade_to_base_and_back(db_url: str) -> None:
    cfg = alembic_config(db_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    engine = make_engine(db_url)
    assert set(inspect(engine).get_table_names()) == {"alembic_version"}
    engine.dispose()
    command.upgrade(cfg, "head")
