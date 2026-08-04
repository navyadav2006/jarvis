"""Plain data types for the memory module.

Kept independent of `orchestrator/`'s `Turn`/`MemoryItem` (which look
similar) on purpose — `core/` must never depend on `orchestrator/`
(see core/voice/ports.py's AssistantHandler for the same rule applied
elsewhere). `orchestrator/memory_adapter.py` is the one place that
translates between the two.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

MemoryKind = Literal["turn", "fact", "summary"]


@dataclass(frozen=True)
class ConversationTurn:
    """One request/response exchange — the memory module's own copy of
    what orchestrator.models.Turn carries, without depending on it.
    """

    request_text: str
    response_text: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class MemoryRecord:
    """One stored memory: a conversation turn, an explicitly stored
    fact, or a session summary.

    `temporary=True` marks it eligible for `forget()` — conversation
    turns default to temporary (ephemeral working memory); explicitly
    stored knowledge and summaries default to durable. `importance` is
    caller-assigned (0.0-1.0), used by ranking.rank_records alongside
    keyword overlap and recency.
    """

    id: int | None
    content: str
    kind: MemoryKind
    session_id: str | None
    importance: float
    created_at: datetime
    last_accessed_at: datetime | None
    temporary: bool
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class MemoryQuery:
    """What recall() is asked for."""

    text: str
    session_id: str | None = None
    limit: int = 5
    kinds: tuple[MemoryKind, ...] | None = None  # None = any kind
