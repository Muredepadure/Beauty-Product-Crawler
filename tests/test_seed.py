import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from beautycrawler.db import Brand, Product, Retailer
from beautycrawler.db.seed import DEMO_PRODUCTS, RETAILERS, seed
from beautycrawler.db.session import make_engine, make_session_factory

REPO_ROOT = Path(__file__).resolve().parents[1]


def count(session: Session, model: type) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_seed_populates_retailers_and_demo(session: Session) -> None:
    result = seed(session)
    assert result.retailers_added == len(RETAILERS) == 10
    assert result.products_added == len(DEMO_PRODUCTS)
    assert count(session, Retailer) == 10
    assert count(session, Product) == len(DEMO_PRODUCTS)
    # Brands deduplicated by folded name (La Roche-Posay appears twice).
    assert count(session, Brand) == len({b for b, *_ in DEMO_PRODUCTS})
    notino = session.scalars(select(Retailer).where(Retailer.slug == "notino")).one()
    assert (notino.domain, notino.is_active) == ("notino.ro", True)
    loreal = session.scalars(select(Brand).where(Brand.name == "L'Oréal Paris")).one()
    assert loreal.normalized_name == "l'oreal paris"


def test_seed_is_idempotent(session: Session) -> None:
    seed(session)
    again = seed(session)
    assert (again.retailers_added, again.brands_added, again.products_added) == (0, 0, 0)
    assert count(session, Retailer) == 10


def test_seed_keeps_existing_rows(session: Session) -> None:
    session.add(Retailer(slug="notino", name="Notino (custom)", domain="notino.ro"))
    session.commit()
    result = seed(session, demo=False)
    assert result.retailers_added == 9
    assert result.products_added == 0
    notino = session.scalars(select(Retailer).where(Retailer.slug == "notino")).one()
    assert notino.name == "Notino (custom)"


def test_demo_data_has_no_fabricated_identifiers(session: Session) -> None:
    seed(session)
    assert all(p.ean is None and not p.offers for p in session.scalars(select(Product)))


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("seed_script", REPO_ROOT / "scripts/seed.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_seed_script_against_migrated_db(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    url = f"sqlite:///{tmp_path / 'seed.db'}"
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")

    script = load_script()
    assert script.main(["--database-url", url]) == 0
    assert "10 retailers" in capsys.readouterr().out
    assert script.main(["--database-url", url]) == 0
    assert "0 retailers, 0 brands, 0 products" in capsys.readouterr().out

    engine = make_engine(url)
    with make_session_factory(engine)() as s:
        assert count(s, Retailer) == 10
    engine.dispose()
