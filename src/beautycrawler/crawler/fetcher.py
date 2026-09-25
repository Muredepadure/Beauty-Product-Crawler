"""Polite async HTTP fetcher shared by all spiders.

Rules (CLAUDE.md, "Polite crawling"):

- robots.txt is checked before every request, including each redirect hop, and cached
  per origin. Per RFC 9309: a 4xx robots.txt means no restrictions; a 5xx or network
  error means "disallow everything" until the (shorter) error cache expires.
- One request at a time per host, at least `request_delay_seconds` apart (or the site's
  `Crawl-delay`, whichever is larger).
- Retries with exponential backoff on timeouts, connection errors, 429 and 5xx, honoring
  `Retry-After`. Other 4xx are returned to the caller without retrying.
- Bot-protection pages (e.g. a Cloudflare challenge) raise `BlockedError` and are never
  retried or worked around.
- Every request carries the configured User-Agent.
"""

import asyncio
import time
import urllib.robotparser
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from types import TracebackType
from typing import Self
from urllib.parse import urljoin, urlsplit

import httpx

from beautycrawler.config import Settings, get_settings

MAX_REDIRECTS = 5
MAX_RETRY_AFTER_SECONDS = 300.0
ROBOTS_ERROR_TTL_SECONDS = 600.0
RETRY_STATUSES = frozenset({408, 429, 500, 502, 503, 504})

Sleep = Callable[[float], Awaitable[None]]
Clock = Callable[[], float]


class FetchError(Exception):
    """The URL could not be fetched (after retries)."""

    def __init__(self, url: str, message: str) -> None:
        super().__init__(f"{url}: {message}")
        self.url = url


class RobotsDisallowedError(FetchError):
    """robots.txt forbids this URL for our User-Agent."""


class BlockedError(FetchError):
    """The site answered with a bot-protection challenge; we don't bypass these."""


@dataclass(frozen=True, slots=True)
class FetchResult:
    url: str  # final URL after redirects
    status_code: int
    text: str
    headers: httpx.Headers

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300


@dataclass(slots=True)
class _Robots:
    parser: urllib.robotparser.RobotFileParser | None  # None = disallow all
    allow_all: bool
    expires_at: float


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}".lower()


def looks_like_bot_challenge(response: httpx.Response) -> bool:
    """Heuristic for interstitial bot checks (Cloudflare and similar)."""
    if response.headers.get("cf-mitigated", "").lower() == "challenge":
        return True
    if response.status_code in (403, 429, 503):
        body = response.text[:5000].lower()
        markers = ("challenge-platform", "cf-chl-", "just a moment...", "captcha")
        return any(m in body for m in markers)
    return False


def _retry_after_seconds(value: str | None, now: datetime | None = None) -> float | None:
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    now = now or datetime.now(UTC)
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - now).total_seconds())


class PoliteFetcher:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: httpx.AsyncClient | None = None,
        sleep: Sleep = asyncio.sleep,
        clock: Clock = time.monotonic,
    ) -> None:
        self.settings = settings or get_settings()
        self._own_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=self.settings.request_timeout_seconds, follow_redirects=False
        )
        self._sleep = sleep
        self._clock = clock
        self._robots: dict[str, _Robots] = {}
        self._robots_locks: dict[str, asyncio.Lock] = {}
        self._host_locks: dict[str, asyncio.Lock] = {}
        self._last_request_at: dict[str, float] = {}

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._own_client:
            await self._client.aclose()

    # ------------------------------------------------------------------ public API

    async def fetch(self, url: str) -> FetchResult:
        """GET `url` politely, following up to MAX_REDIRECTS redirects.

        Raises RobotsDisallowedError, BlockedError or FetchError. Non-retryable HTTP
        errors (e.g. 404) are returned as a FetchResult with that status.
        """
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            if not await self.allowed(current):
                raise RobotsDisallowedError(current, "disallowed by robots.txt")
            response = await self._get_with_retries(current, delay=await self.crawl_delay(current))
            if response.is_redirect and "location" in response.headers:
                current = urljoin(current, response.headers["location"])
                continue
            return FetchResult(
                url=current,
                status_code=response.status_code,
                text=response.text,
                headers=response.headers,
            )
        raise FetchError(url, f"more than {MAX_REDIRECTS} redirects")

    async def allowed(self, url: str) -> bool:
        robots = await self._get_robots(_origin(url))
        if robots.allow_all:
            return True
        if robots.parser is None:
            return False
        return robots.parser.can_fetch(self.settings.user_agent, url)

    async def crawl_delay(self, url: str) -> float:
        """Seconds to wait between requests to this URL's host."""
        delay = self.settings.request_delay_seconds
        robots = await self._get_robots(_origin(url))
        if robots.parser is not None:
            site_delay = robots.parser.crawl_delay(self.settings.user_agent)
            if site_delay is not None:
                delay = max(delay, float(site_delay))
        return delay

    # ------------------------------------------------------------------ internals

    async def _get_robots(self, origin: str) -> _Robots:
        lock = self._robots_locks.setdefault(origin, asyncio.Lock())
        async with lock:
            cached = self._robots.get(origin)
            if cached is not None and cached.expires_at > self._clock():
                return cached
            robots = await self._load_robots(origin)
            self._robots[origin] = robots
            return robots

    async def _load_robots(self, origin: str) -> _Robots:
        ttl = float(self.settings.robots_cache_ttl_seconds)
        robots_url = f"{origin}/robots.txt"
        # robots.txt itself uses the configured minimum delay (its Crawl-delay isn't known yet).
        delay = self.settings.request_delay_seconds
        try:
            response = await self._get_with_retries(robots_url, delay=delay)
            # Follow a few same-site redirects (e.g. http -> https, www).
            hops = 0
            while response.is_redirect and "location" in response.headers and hops < 5:
                robots_url = urljoin(robots_url, response.headers["location"])
                response = await self._get_with_retries(robots_url, delay=delay)
                hops += 1
        except FetchError:
            return _Robots(None, False, self._clock() + ROBOTS_ERROR_TTL_SECONDS)

        if 200 <= response.status_code < 300:
            parser = urllib.robotparser.RobotFileParser()
            parser.parse(response.text.splitlines())
            return _Robots(parser, False, self._clock() + ttl)
        if 400 <= response.status_code < 500:
            return _Robots(None, True, self._clock() + ttl)
        # 5xx (after retries) or anything unexpected: be conservative, retry later.
        return _Robots(None, False, self._clock() + ROBOTS_ERROR_TTL_SECONDS)

    async def _wait_for_slot(self, host: str, delay: float) -> None:
        last = self._last_request_at.get(host)
        if last is not None:
            remaining = last + delay - self._clock()
            if remaining > 0:
                await self._sleep(remaining)
        self._last_request_at[host] = self._clock()

    async def _get_with_retries(self, url: str, *, delay: float) -> httpx.Response:
        """GET with per-host spacing of at least `delay` seconds, and retries."""
        host = urlsplit(url).netloc.lower()
        headers = {"User-Agent": self.settings.user_agent, "Accept-Language": "ro-RO,ro;q=0.9"}
        attempts = self.settings.max_retries + 1
        lock = self._host_locks.setdefault(host, asyncio.Lock())

        for attempt in range(attempts):
            backoff = self.settings.retry_backoff_seconds * (2**attempt)
            async with lock:
                await self._wait_for_slot(host, delay)
                try:
                    response = await self._client.get(url, headers=headers)
                except httpx.TransportError as exc:
                    if attempt + 1 >= attempts:
                        raise FetchError(url, f"{type(exc).__name__}: {exc}") from exc
                    await self._sleep(backoff)
                    continue

            if looks_like_bot_challenge(response):
                raise BlockedError(url, f"bot-protection challenge (HTTP {response.status_code})")
            if response.status_code in RETRY_STATUSES and attempt + 1 < attempts:
                retry_after = _retry_after_seconds(response.headers.get("retry-after"))
                wait = backoff if retry_after is None else min(retry_after, MAX_RETRY_AFTER_SECONDS)
                await self._sleep(max(wait, backoff))
                continue
            return response
        raise AssertionError("unreachable")  # pragma: no cover
