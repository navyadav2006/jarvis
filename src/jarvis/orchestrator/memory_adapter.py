"""MemoryManagerAdapter: bridges core/memory/'s MemoryManagerPort to
orchestrator.ports.MemoryPort's shape, so Orchestrator (which only
knows about Turn/MemoryItem) can use SqliteMemoryManager without
core/memory/ ever importing orchestrator/ — the same one-way dependency
rule every prior phase has followed (core/voice/'s AssistantHandler,
core/cowork/'s models.py, etc.).

`MemoryItem.score` is set to the record's stored `importance`, not the
full multi-factor rank score `ranking.py` computes internally during
recall() — orchestrator/ only needs "how confident is this," and
exposing the intermediate ranking math isn't part of MemoryPort's
contract.
"""

from __future__ import annotations

from jarvis.core.memory.ports import MemoryManagerPort
from jarvis.core.memory.types import ConversationTurn, MemoryQuery
from jarvis.orchestrator.models import Turn
from jarvis.orchestrator.ports import MemoryItem


class MemoryManagerAdapter:
    """Implements orchestrator.ports.MemoryPort."""

    def __init__(self, manager: MemoryManagerPort) -> None:
        self._manager = manager

    def recall(self, session_id: str, query: str, *, limit: int = 5) -> list[MemoryItem]:
        records = self._manager.recall(
            MemoryQuery(text=query, session_id=session_id, limit=limit)
        )
        return [
            MemoryItem(
                content=record.content,
                score=record.importance,
                metadata={"kind": record.kind, "id": record.id},
            )
            for record in records
        ]

    def remember(self, session_id: str, turn: Turn) -> None:
        self._manager.remember_turn(
            session_id,
            ConversationTurn(
                request_text=turn.request_text,
                response_text=turn.response_text,
                timestamp=turn.timestamp,
            ),
        )
