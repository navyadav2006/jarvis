from __future__ import annotations

from datetime import UTC, datetime

from jarvis.core.config.memory_config import LongTermMemoryConfig
from jarvis.core.memory.store import SqliteMemoryManager
from jarvis.orchestrator.memory_adapter import MemoryManagerAdapter
from jarvis.orchestrator.models import Turn
from jarvis.orchestrator.ports import MemoryPort


def _adapter(tmp_path) -> MemoryManagerAdapter:
    config = LongTermMemoryConfig(database_path=tmp_path / "memory.db")
    return MemoryManagerAdapter(SqliteMemoryManager(config))


def test_adapter_satisfies_memory_port(tmp_path) -> None:
    assert isinstance(_adapter(tmp_path), MemoryPort)


def test_remember_then_recall_round_trips_as_memory_item(tmp_path) -> None:
    adapter = _adapter(tmp_path)
    turn = Turn(
        request_text="turn on the lights",
        response_text="done",
        intent_name="lights_on",
        timestamp=datetime.now(UTC),
    )

    adapter.remember("s1", turn)
    results = adapter.recall("s1", "lights")

    assert len(results) == 1
    assert "turn on the lights" in results[0].content
    assert results[0].metadata["kind"] == "turn"
