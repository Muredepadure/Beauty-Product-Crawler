"""Application settings, read from environment variables and an optional `.env` file.

All variables are documented in `.env.example`. `DATABASE_URL` is read unprefixed
(the conventional name); everything else uses the `BEAUTYCRAWLER_` prefix.
"""

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_USER_AGENT = "BeautyCrawler/0.1 (+https://github.com/Muredepadure/Beauty-Product-Crawler)"

# Polite-crawling floor from CLAUDE.md: never less than 2 s between requests to one domain.
MIN_REQUEST_DELAY_SECONDS = 2.0


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BEAUTYCRAWLER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        default="sqlite:///beautycrawler.db",
        validation_alias=AliasChoices("DATABASE_URL", "BEAUTYCRAWLER_DATABASE_URL"),
        description="SQLAlchemy URL. SQLite for dev; e.g. postgresql+psycopg://... in prod.",
    )
    user_agent: str = Field(default=DEFAULT_USER_AGENT, min_length=1)
    request_delay_seconds: float = Field(
        default=MIN_REQUEST_DELAY_SECONDS,
        ge=MIN_REQUEST_DELAY_SECONDS,
        description="Minimum delay between two requests to the same domain.",
    )
    request_timeout_seconds: float = Field(default=30.0, gt=0)
    max_retries: int = Field(default=3, ge=0, le=10)
    retry_backoff_seconds: float = Field(
        default=2.0, gt=0, description="Base for exponential backoff between retries."
    )
    robots_cache_ttl_seconds: int = Field(default=24 * 3600, ge=0)
    api_base_url: str = Field(
        default="http://localhost:8000/api", description="Used by the Streamlit UI."
    )


@lru_cache
def get_settings() -> Settings:
    """Process-wide settings instance. Call `get_settings.cache_clear()` in tests."""
    return Settings()
