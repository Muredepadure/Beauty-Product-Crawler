"""P8.1: static checks that the Docker/compose setup matches the code base.

(The image itself is built and run by hand / in deployment; tests never need Docker.)
"""

from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def compose() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((ROOT / "docker-compose.yml").read_text("utf-8"))
    return data


def _command(service: dict[str, Any]) -> str:
    command = service.get("command", [])
    return " ".join(command) if isinstance(command, list) else str(command)


def test_services(compose: dict[str, Any]) -> None:
    assert set(compose["services"]) == {"db", "migrate", "api", "ui", "scheduler"}


def test_app_services_share_database_url(compose: dict[str, Any]) -> None:
    for name in ("migrate", "api", "ui", "scheduler"):
        url = compose["services"][name]["environment"]["DATABASE_URL"]
        assert url.startswith("postgresql+psycopg://"), name
        assert "@db:5432/" in url, name


def test_startup_order(compose: dict[str, Any]) -> None:
    services = compose["services"]
    assert services["migrate"]["depends_on"]["db"]["condition"] == "service_healthy"
    for name in ("api", "scheduler"):
        condition = services[name]["depends_on"]["migrate"]["condition"]
        assert condition == "service_completed_successfully", name
    assert services["ui"]["environment"]["BEAUTYCRAWLER_API_BASE_URL"] == "http://api:8000/api"


def test_commands_reference_real_entry_points(compose: dict[str, Any]) -> None:
    services = compose["services"]
    assert "alembic upgrade head" in _command(services["migrate"])
    assert (ROOT / "scripts" / "seed.py").is_file()
    assert "beautycrawler.api.main:app" in _command(services["api"])
    assert "ui/App.py" in _command(services["ui"])
    assert (ROOT / "ui" / "App.py").is_file()
    scheduler = _command(services["scheduler"])
    assert "python -m beautycrawler.crawler" in scheduler
    assert "run --all --due --match" in scheduler


def test_dockerfile_copies_what_services_use() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text("utf-8")
    for path in ("src", "alembic.ini", "scripts", "ui"):
        assert f"COPY {path} " in dockerfile, path
    assert "USER app" in dockerfile  # not root
    ignored = (ROOT / ".dockerignore").read_text("utf-8").split()
    assert ".env" in ignored and ".git" in ignored  # no secrets or history in the image
