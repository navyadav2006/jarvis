from __future__ import annotations

from datetime import UTC, datetime

from jarvis.orchestrator.models import Turn
from jarvis.orchestrator.session_store import SessionStore


def test_get_or_create_creates_new_session(session_store: SessionStore) -> None:
    session = session_store.get_or_create("s1")
    assert session.session_id == "s1"
    assert session.history == []


def test_get_or_create_returns_same_session_on_repeat_calls(session_store: SessionStore) -> None:
    first = session_store.get_or_create("s1")
    second = session_store.get_or_create("s1")
    assert first is second


def test_get_returns_none_for_unknown_session(session_store: SessionStore) -> None:
    assert session_store.get("nope") is None


def test_clear_removes_session(session_store: SessionStore) -> None:
    session_store.get_or_create("s1")
    session_store.clear("s1")
    assert session_store.get("s1") is None


def test_session_ids_lists_all_active_sessions(session_store: SessionStore) -> None:
    session_store.get_or_create("s1")
    session_store.get_or_create("s2")
    assert set(session_store.session_ids()) == {"s1", "s2"}


def test_session_history_caps_at_max_history(session_store: SessionStore) -> None:
    session = session_store.get_or_create("s1")
    session.max_history = 2
    for i in range(5):
        session.add_turn(
            Turn(
                request_text=str(i),
                response_text="",
                intent_name="x",
                timestamp=datetime.now(UTC),
            )
        )
    assert len(session.history) == 2
    assert [t.request_text for t in session.history] == ["3", "4"]
