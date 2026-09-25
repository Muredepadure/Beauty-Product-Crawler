import asyncio
import itertools
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
import respx
from conftest import UA, FakeTime

from beautycrawler.config import Settings
from beautycrawler.crawler.fetcher import (
    BlockedError,
    FetchError,
    PoliteFetcher,
    RobotsDisallowedError,
    _retry_after_seconds,
)

SHOP = "https://shop.example.ro"
ROBOTS = "User-agent: *\nDisallow: /cos\nDisallow: /cont/\n"


@pytest.fixture
def mock() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        yield router


@pytest.fixture
async def fetcher(settings: Settings, fake_time: FakeTime) -> AsyncIterator[PoliteFetcher]:
    async with PoliteFetcher(settings, sleep=fake_time.sleep, clock=fake_time.clock) as f:
        yield f


def robots(mock: respx.MockRouter, text: str = ROBOTS, status: int = 200) -> respx.Route:
    return mock.get(f"{SHOP}/robots.txt").mock(return_value=httpx.Response(status, text=text))


async def test_fetch_ok_sends_user_agent(fetcher: PoliteFetcher, mock: respx.MockRouter) -> None:
    robots(mock)
    page = mock.get(f"{SHOP}/p/1").mock(return_value=httpx.Response(200, text="<html>ok</html>"))
    result = await fetcher.fetch(f"{SHOP}/p/1")
    assert result.ok and result.text == "<html>ok</html>" and result.url == f"{SHOP}/p/1"
    assert page.calls.last.request.headers["user-agent"] == UA


async def test_robots_disallow(fetcher: PoliteFetcher, mock: respx.MockRouter) -> None:
    robots(mock)
    page = mock.get(f"{SHOP}/cos").mock(return_value=httpx.Response(200))
    with pytest.raises(RobotsDisallowedError):
        await fetcher.fetch(f"{SHOP}/cos")
    assert not page.called
    assert await fetcher.allowed(f"{SHOP}/cont/login") is False
    assert await fetcher.allowed(f"{SHOP}/produs/x") is True


async def test_robots_specific_user_agent_group(settings: Settings, fake_time: FakeTime) -> None:
    text = "User-agent: BeautyCrawlerTest\nDisallow: /\n\nUser-agent: *\nAllow: /\n"
    with respx.mock() as mock:
        robots(mock, text)
        async with PoliteFetcher(settings, sleep=fake_time.sleep, clock=fake_time.clock) as f:
            assert await f.allowed(f"{SHOP}/p/1") is False


async def test_robots_cached(fetcher: PoliteFetcher, mock: respx.MockRouter) -> None:
    route = robots(mock)
    mock.get(url__startswith=f"{SHOP}/p/").mock(return_value=httpx.Response(200))
    for i in range(3):
        await fetcher.fetch(f"{SHOP}/p/{i}")
    assert route.call_count == 1


async def test_robots_cache_expires(
    fetcher: PoliteFetcher, mock: respx.MockRouter, fake_time: FakeTime
) -> None:
    route = robots(mock)
    await fetcher.allowed(f"{SHOP}/p/1")
    fake_time.now += 3601
    await fetcher.allowed(f"{SHOP}/p/1")
    assert route.call_count == 2


@pytest.mark.parametrize("status", [401, 403, 404, 410])
async def test_robots_4xx_means_allow_all(
    fetcher: PoliteFetcher, mock: respx.MockRouter, status: int
) -> None:
    robots(mock, "", status)
    assert await fetcher.allowed(f"{SHOP}/cos") is True


async def test_robots_5xx_means_disallow_all(
    fetcher: PoliteFetcher, mock: respx.MockRouter, fake_time: FakeTime
) -> None:
    route = robots(mock, "", 503)
    with pytest.raises(RobotsDisallowedError):
        await fetcher.fetch(f"{SHOP}/p/1")
    assert route.call_count == 3  # retried, then gave up
    # Error result is cached only briefly, then robots.txt is tried again.
    route.mock(return_value=httpx.Response(200, text=ROBOTS))
    fake_time.now += 601
    assert await fetcher.allowed(f"{SHOP}/p/1") is True


async def test_robots_network_error_means_disallow(
    fetcher: PoliteFetcher, mock: respx.MockRouter
) -> None:
    mock.get(f"{SHOP}/robots.txt").mock(side_effect=httpx.ConnectError("boom"))
    assert await fetcher.allowed(f"{SHOP}/p/1") is False


async def test_robots_redirect_followed(fetcher: PoliteFetcher, mock: respx.MockRouter) -> None:
    mock.get(f"{SHOP}/robots.txt").mock(
        return_value=httpx.Response(
            301, headers={"location": "https://www.shop.example.ro/robots.txt"}
        )
    )
    mock.get("https://www.shop.example.ro/robots.txt").mock(
        return_value=httpx.Response(200, text=ROBOTS)
    )
    assert await fetcher.allowed(f"{SHOP}/cos") is False


async def test_delay_between_requests_same_host(
    fetcher: PoliteFetcher, mock: respx.MockRouter, fake_time: FakeTime
) -> None:
    robots(mock)
    mock.get(url__startswith=f"{SHOP}/p/").mock(return_value=httpx.Response(200))
    for i in range(3):
        await fetcher.fetch(f"{SHOP}/p/{i}")
    # robots.txt, then 3 pages: every request at least 2 s after the previous one.
    assert fake_time.sleeps == [2.0, 2.0, 2.0]


async def test_crawl_delay_from_robots_is_respected(
    fetcher: PoliteFetcher, mock: respx.MockRouter, fake_time: FakeTime
) -> None:
    robots(mock, "User-agent: *\nCrawl-delay: 10\n")
    mock.get(url__startswith=f"{SHOP}/p/").mock(return_value=httpx.Response(200))
    await fetcher.fetch(f"{SHOP}/p/1")
    await fetcher.fetch(f"{SHOP}/p/2")
    assert fake_time.sleeps == [10.0, 10.0]
    assert await fetcher.crawl_delay(f"{SHOP}/p/3") == 10.0


async def test_crawl_delay_never_below_configured_minimum(
    fetcher: PoliteFetcher, mock: respx.MockRouter
) -> None:
    robots(mock, "User-agent: *\nCrawl-delay: 0.5\n")
    assert await fetcher.crawl_delay(f"{SHOP}/p/1") == 2.0


async def test_no_delay_needed_when_time_already_passed(
    fetcher: PoliteFetcher, mock: respx.MockRouter, fake_time: FakeTime
) -> None:
    robots(mock)
    mock.get(url__startswith=f"{SHOP}/p/").mock(return_value=httpx.Response(200))
    await fetcher.fetch(f"{SHOP}/p/1")
    fake_time.sleeps.clear()
    fake_time.now += 60
    await fetcher.fetch(f"{SHOP}/p/2")
    assert fake_time.sleeps == []


async def test_hosts_are_rate_limited_independently(
    fetcher: PoliteFetcher, mock: respx.MockRouter, fake_time: FakeTime
) -> None:
    other = "https://other.example.ro"
    robots(mock)
    mock.get(f"{other}/robots.txt").mock(return_value=httpx.Response(404))
    mock.get(f"{SHOP}/p/1").mock(return_value=httpx.Response(200))
    mock.get(f"{other}/p/1").mock(return_value=httpx.Response(200))
    await fetcher.fetch(f"{SHOP}/p/1")
    await fetcher.fetch(f"{other}/p/1")
    # One wait per host (page after its robots.txt); no cross-host waiting.
    assert fake_time.sleeps == [2.0, 2.0]


async def test_concurrent_requests_to_one_host_are_serialized(
    settings: Settings, mock: respx.MockRouter
) -> None:
    """With the real clock, parallel fetches to one host still go out one per delay."""
    # model_copy skips validation, so the delay can go below the 2 s floor for this test only.
    fast = settings.model_copy(update={"request_delay_seconds": 0.05})
    robots(mock)
    sent: list[float] = []
    loop = asyncio.get_running_loop()

    def record(request: httpx.Request) -> httpx.Response:
        sent.append(loop.time())
        return httpx.Response(200)

    mock.get(url__startswith=f"{SHOP}/p/").mock(side_effect=record)
    async with PoliteFetcher(fast) as f:
        await asyncio.gather(*(f.fetch(f"{SHOP}/p/{i}") for i in range(4)))
    gaps = [b - a for a, b in itertools.pairwise(sent)]
    assert len(sent) == 4
    assert all(g >= 0.045 for g in gaps), gaps


async def test_retries_5xx_then_succeeds(
    fetcher: PoliteFetcher, mock: respx.MockRouter, fake_time: FakeTime
) -> None:
    robots(mock)
    route = mock.get(f"{SHOP}/p/1").mock(
        side_effect=[httpx.Response(502), httpx.Response(503), httpx.Response(200, text="ok")]
    )
    result = await fetcher.fetch(f"{SHOP}/p/1")
    assert result.text == "ok" and route.call_count == 3
    # 2 s slot; 1 s backoff + 1 s to complete the 2 s slot; 2 s backoff (slot already free)
    assert fake_time.sleeps == [2.0, 1.0, 1.0, 2.0]


async def test_gives_up_after_max_retries_returns_last_response(
    fetcher: PoliteFetcher, mock: respx.MockRouter
) -> None:
    robots(mock)
    route = mock.get(f"{SHOP}/p/1").mock(return_value=httpx.Response(500))
    result = await fetcher.fetch(f"{SHOP}/p/1")
    assert result.status_code == 500 and not result.ok
    assert route.call_count == 3  # 1 + max_retries


async def test_transport_errors_retried_then_raise(
    fetcher: PoliteFetcher, mock: respx.MockRouter
) -> None:
    robots(mock)
    route = mock.get(f"{SHOP}/p/1").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(FetchError, match="ReadTimeout"):
        await fetcher.fetch(f"{SHOP}/p/1")
    assert route.call_count == 3


async def test_404_not_retried(fetcher: PoliteFetcher, mock: respx.MockRouter) -> None:
    robots(mock)
    route = mock.get(f"{SHOP}/p/gone").mock(return_value=httpx.Response(404))
    result = await fetcher.fetch(f"{SHOP}/p/gone")
    assert result.status_code == 404 and route.call_count == 1


async def test_429_honors_retry_after(
    fetcher: PoliteFetcher, mock: respx.MockRouter, fake_time: FakeTime
) -> None:
    robots(mock)
    mock.get(f"{SHOP}/p/1").mock(
        side_effect=[httpx.Response(429, headers={"retry-after": "30"}), httpx.Response(200)]
    )
    await fetcher.fetch(f"{SHOP}/p/1")
    assert 30.0 in fake_time.sleeps


async def test_retry_after_is_capped(
    fetcher: PoliteFetcher, mock: respx.MockRouter, fake_time: FakeTime
) -> None:
    robots(mock)
    mock.get(f"{SHOP}/p/1").mock(
        side_effect=[httpx.Response(503, headers={"retry-after": "86400"}), httpx.Response(200)]
    )
    await fetcher.fetch(f"{SHOP}/p/1")
    assert max(fake_time.sleeps) == 300.0


def test_retry_after_parsing() -> None:
    from datetime import UTC, datetime

    now = datetime(2026, 9, 25, 12, 0, 0, tzinfo=UTC)
    assert _retry_after_seconds("120") == 120.0
    assert _retry_after_seconds("Fri, 25 Sep 2026 12:01:00 GMT", now) == 60.0
    assert _retry_after_seconds("Fri, 25 Sep 2026 11:00:00 GMT", now) == 0.0
    assert _retry_after_seconds("soon") is None
    assert _retry_after_seconds(None) is None


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(403, headers={"cf-mitigated": "challenge"}, text=""),
        httpx.Response(
            503, text="<title>Just a moment...</title><script src=/cdn-cgi/challenge-platform/x>"
        ),
        httpx.Response(403, text="<div class='g-recaptcha'>Please solve the CAPTCHA</div>"),
    ],
)
async def test_bot_challenge_raises_blocked_without_retry(
    fetcher: PoliteFetcher, mock: respx.MockRouter, response: httpx.Response
) -> None:
    robots(mock)
    route = mock.get(f"{SHOP}/p/1").mock(return_value=response)
    with pytest.raises(BlockedError):
        await fetcher.fetch(f"{SHOP}/p/1")
    assert route.call_count == 1


async def test_plain_403_is_returned_not_blocked(
    fetcher: PoliteFetcher, mock: respx.MockRouter
) -> None:
    robots(mock)
    mock.get(f"{SHOP}/p/1").mock(return_value=httpx.Response(403, text="Forbidden"))
    assert (await fetcher.fetch(f"{SHOP}/p/1")).status_code == 403


async def test_redirects_followed_and_each_hop_checked(
    fetcher: PoliteFetcher, mock: respx.MockRouter
) -> None:
    robots(mock)
    mock.get(f"{SHOP}/old").mock(return_value=httpx.Response(301, headers={"location": "/new"}))
    mock.get(f"{SHOP}/new").mock(return_value=httpx.Response(200, text="new"))
    result = await fetcher.fetch(f"{SHOP}/old")
    assert (result.url, result.text) == (f"{SHOP}/new", "new")


async def test_redirect_into_disallowed_path_is_refused(
    fetcher: PoliteFetcher, mock: respx.MockRouter
) -> None:
    robots(mock)
    mock.get(f"{SHOP}/p/1").mock(return_value=httpx.Response(302, headers={"location": "/cos"}))
    target = mock.get(f"{SHOP}/cos").mock(return_value=httpx.Response(200))
    with pytest.raises(RobotsDisallowedError):
        await fetcher.fetch(f"{SHOP}/p/1")
    assert not target.called


async def test_redirect_to_other_host_checks_its_robots(
    fetcher: PoliteFetcher, mock: respx.MockRouter
) -> None:
    robots(mock)
    other_robots = mock.get("https://cdn.example.ro/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nDisallow: /\n")
    )
    mock.get(f"{SHOP}/p/1").mock(
        return_value=httpx.Response(302, headers={"location": "https://cdn.example.ro/p/1"})
    )
    with pytest.raises(RobotsDisallowedError):
        await fetcher.fetch(f"{SHOP}/p/1")
    assert other_robots.called


async def test_redirect_loop_raises(fetcher: PoliteFetcher, mock: respx.MockRouter) -> None:
    robots(mock)
    mock.get(f"{SHOP}/a").mock(return_value=httpx.Response(302, headers={"location": "/b"}))
    mock.get(f"{SHOP}/b").mock(return_value=httpx.Response(302, headers={"location": "/a"}))
    with pytest.raises(FetchError, match="redirects"):
        await fetcher.fetch(f"{SHOP}/a")
