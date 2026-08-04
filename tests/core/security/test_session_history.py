from __future__ import annotations

from jarvis.core.security.session_history import SessionHistory
from jarvis.core.security.types import PermissionLevel, SecurityDecision


def _decision(**overrides) -> SecurityDecision:
    defaults = dict(allowed=True, level=PermissionLevel.READ, reason="allowed")
    defaults.update(overrides)
    return SecurityDecision(**defaults)


def test_records_and_retrieves_per_requester() -> None:
    history = SessionHistory(limit=10)
    history.record("cowork", _decision())
    history.record("cowork", _decision(allowed=False, reason="denied"))

    entries = history.for_requester("cowork")
    assert len(entries) == 2
    assert entries[0].allowed is True
    assert entries[1].reason == "denied"


def test_unknown_requester_returns_empty_list() -> None:
    history = SessionHistory()
    assert history.for_requester("nobody") == []


def test_requesters_are_isolated() -> None:
    history = SessionHistory()
    history.record("cowork", _decision())
    assert history.for_requester("other-plugin") == []


def test_history_is_bounded_by_limit() -> None:
    history = SessionHistory(limit=3)
    for i in range(5):
        history.record("cowork", _decision(reason=str(i)))

    entries = history.for_requester("cowork")
    assert len(entries) == 3
    assert [e.reason for e in entries] == ["2", "3", "4"]


def test_clear_removes_a_requesters_history() -> None:
    history = SessionHistory()
    history.record("cowork", _decision())
    history.clear("cowork")
    assert history.for_requester("cowork") == []
