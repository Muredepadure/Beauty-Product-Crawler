from collections.abc import Callable

import pytest

from beautycrawler.crawler import awake


def recorder(calls: list[int]) -> Callable[[int], bool]:
    """A stand-in for `_set_state` that records the flags and reports success."""

    def set_state(flags: int) -> bool:
        calls.append(flags)
        return True

    return set_state


def test_keep_awake_sets_and_clears_the_request(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []
    monkeypatch.setattr(awake, "_set_state", recorder(calls))
    with awake.keep_awake() as active:
        assert active
        assert calls == [awake.ES_CONTINUOUS | awake.ES_SYSTEM_REQUIRED | awake.ES_DISPLAY_REQUIRED]
    assert calls[-1] == awake.ES_CONTINUOUS  # cleared afterwards


def test_keep_awake_disabled_does_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []
    monkeypatch.setattr(awake, "_set_state", recorder(calls))
    with awake.keep_awake(False) as active:
        assert not active
    assert calls == []


def test_keep_awake_is_cleared_after_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []
    monkeypatch.setattr(awake, "_set_state", recorder(calls))
    with pytest.raises(RuntimeError), awake.keep_awake():
        raise RuntimeError("crawl failed")
    assert calls[-1] == awake.ES_CONTINUOUS
