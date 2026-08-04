from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core.config.memory_config import LongTermMemoryConfig
from jarvis.core.memory.store import SqliteMemoryManager
from jarvis.core.memory.types import ConversationTurn, MemoryQuery


@pytest.fixture
def manager(tmp_path: Path) -> SqliteMemoryManager:
    config = LongTermMemoryConfig(database_path=tmp_path / "memory.db")
    m = SqliteMemoryManager(config)
    yield m
    m.close()


def test_remember_turn_persists_and_is_recallable(manager: SqliteMemoryManager) -> None:
    manager.remember_turn(
        "s1", ConversationTurn(request_text="turn on the lights", response_text="done")
    )
    results = manager.recall(MemoryQuery(text="lights", session_id="s1"))
    assert len(results) == 1
    assert "turn on the lights" in results[0].content
    assert results[0].kind == "turn"
    assert results[0].temporary is True


def test_store_knowledge_defaults_to_durable(manager: SqliteMemoryManager) -> None:
    record = manager.store_knowledge("user prefers dark mode", tags=("preference",))
    assert record.temporary is False
    assert record.kind == "fact"
    assert record.tags == ("preference",)


def test_recall_filters_by_session_id(manager: SqliteMemoryManager) -> None:
    manager.remember_turn("s1", ConversationTurn(request_text="hello s1", response_text="hi"))
    manager.remember_turn("s2", ConversationTurn(request_text="hello s2", response_text="hi"))

    results = manager.recall(MemoryQuery(text="hello", session_id="s1", limit=10))

    assert len(results) == 1
    assert "s1" in results[0].content


def test_recall_ranks_by_relevance_not_insertion_order(manager: SqliteMemoryManager) -> None:
    manager.store_knowledge("the sky is blue", importance=0.1)
    manager.store_knowledge("the kitchen lights are broken", importance=0.9)

    results = manager.recall(MemoryQuery(text="kitchen lights", limit=10))

    assert "kitchen lights" in results[0].content


def test_recall_respects_limit(manager: SqliteMemoryManager) -> None:
    for i in range(5):
        manager.store_knowledge(f"fact number {i}")
    results = manager.recall(MemoryQuery(text="fact", limit=2))
    assert len(results) == 2


def test_summarize_session_returns_readable_text(manager: SqliteMemoryManager) -> None:
    manager.remember_turn(
        "s1", ConversationTurn(request_text="turn on the lights", response_text="done")
    )
    manager.remember_turn(
        "s1", ConversationTurn(request_text="what's the weather", response_text="sunny")
    )

    summary = manager.summarize_session("s1")

    assert "s1" in summary
    assert "2 turn" in summary


def test_summarize_session_is_stored_as_a_durable_summary_record(
    manager: SqliteMemoryManager,
) -> None:
    manager.remember_turn("s1", ConversationTurn(request_text="hi", response_text="hello"))
    manager.summarize_session("s1")

    results = manager.recall(MemoryQuery(text="s1", session_id="s1", kinds=("summary",)))
    assert len(results) == 1
    assert results[0].temporary is False


def test_forget_removes_only_temporary_records_by_default(manager: SqliteMemoryManager) -> None:
    manager.remember_turn("s1", ConversationTurn(request_text="hi", response_text="hello"))
    manager.store_knowledge("durable fact")

    deleted = manager.forget(session_id="s1")

    assert deleted == 1
    remaining = manager.recall(MemoryQuery(text="fact", limit=10))
    assert len(remaining) == 1
    assert remaining[0].kind == "fact"


def test_forget_can_remove_durable_records_when_requested(manager: SqliteMemoryManager) -> None:
    manager.store_knowledge("durable fact")
    deleted = manager.forget(temporary_only=False)
    assert deleted == 1


def test_get_by_ids_returns_matching_records(manager: SqliteMemoryManager) -> None:
    a = manager.store_knowledge("fact a")
    manager.store_knowledge("fact b")

    results = manager.get_by_ids([a.id])

    assert len(results) == 1
    assert results[0].content == "fact a"


def test_get_by_ids_empty_list_returns_empty(manager: SqliteMemoryManager) -> None:
    assert manager.get_by_ids([]) == []


def test_memory_survives_reconnect(tmp_path: Path) -> None:
    config = LongTermMemoryConfig(database_path=tmp_path / "memory.db")
    first = SqliteMemoryManager(config)
    first.store_knowledge("persisted fact")
    first.close()

    second = SqliteMemoryManager(config)
    results = second.recall(MemoryQuery(text="persisted", limit=10))
    assert len(results) == 1
    second.close()
