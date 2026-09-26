import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from beautycrawler.config import DEFAULT_USER_AGENT, Settings, get_settings


@pytest.fixture(autouse=True)
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run each test in an empty dir (no stray .env) with no relevant env vars set."""
    monkeypatch.chdir(tmp_path)
    for name in list(os.environ):
        if name == "DATABASE_URL" or name.startswith("BEAUTYCRAWLER_"):
            monkeypatch.delenv(name)
    get_settings.cache_clear()


def test_defaults() -> None:
    s = Settings()
    assert s.database_url == "sqlite:///beautycrawler.db"
    assert s.user_agent == DEFAULT_USER_AGENT
    assert s.request_delay_seconds == 2.0
    assert s.max_retries == 3


def test_database_url_unprefixed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db/beauty")
    assert Settings().database_url == "postgresql+psycopg://u:p@db/beauty"


def test_prefixed_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BEAUTYCRAWLER_USER_AGENT", "TestBot/1.0")
    monkeypatch.setenv("BEAUTYCRAWLER_REQUEST_DELAY_SECONDS", "5")
    s = Settings()
    assert s.user_agent == "TestBot/1.0"
    assert s.request_delay_seconds == 5.0


def test_dotenv_file_is_read(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("DATABASE_URL=sqlite:///from-dotenv.db\n", encoding="utf-8")
    assert Settings().database_url == "sqlite:///from-dotenv.db"


def test_delay_below_polite_floor_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BEAUTYCRAWLER_REQUEST_DELAY_SECONDS", "0.5")
    with pytest.raises(ValidationError):
        Settings()


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()


def test_env_example_documents_every_setting() -> None:
    example = Path(__file__).resolve().parents[1] / ".env.example"
    text = example.read_text(encoding="utf-8")
    for name in Settings.model_fields:
        env_name = "DATABASE_URL" if name == "database_url" else f"BEAUTYCRAWLER_{name.upper()}"
        assert f"{env_name}=" in text, f"{env_name} missing from .env.example"
