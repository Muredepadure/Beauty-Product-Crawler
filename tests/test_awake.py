import pytest

from beautycrawler.crawler import awake


def test_keep_awake_sets_and_clears_the_request(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []
    monkeypatch.setattr(awake, "_set_state", lambda flags: calls.append(flags) or True)
    with awake.keep_awake() as active:
        assert active
        assert calls == [awake.ES_CONTINUOUS | awake.ES_SYSTEM_REQUIRED | awake.ES_DISPLAY_REQUIRED]
    assert calls[-1] == awake.ES_CONTINUOUS  # cleared afterwards


def test_keep_awake_disabled_does_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []
    monkeypatch.setattr(awake, "_set_state", lambda flags: calls.append(flags) or True)
    with awake.keep_awake(False) as active:
        assert not active
    assert calls == []


def test_keep_awake_is_cleared_after_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []
    monkeypatch.setattr(awake, "_set_state", lambda flags: calls.append(flags) or True)
    with pytest.raises(RuntimeError), awake.keep_awake():
        raise RuntimeError("crawl failed")
    assert calls[-1] == awake.ES_CONTINUOUS
