"""Abstract interfaces for the memory module.

`MemoryManagerPort` is the structured API Jarvis calls directly — the
Memory Manager collaborator's six responsibilities (maintain long-term
memory, retrieve relevant memories, rank importance, summarize
conversations, store useful knowledge, forget temporary information)
as typed methods, not prose. This is deliberately separate from
core/cowork/collaborators.py's `CollaboratorRole.MEMORY_MANAGER` spec:
that one is a prompt template for asking *Cowork* to reason about what
should be remembered; this one is the real local component that
actually stores and retrieves it. Cowork's Memory Manager collaborator
can recommend an action; only this module (called by Jarvis) performs
one — the same "Cowork proposes, Jarvis executes" boundary Phase 9
already established for automation.

`EmbeddingIndexPort` prepares the interface for future semantic memory
without implementing it — Phase 3's `VectorIndexConfig` already
reserved the config shape (embedding_dim, index_path) for exactly this
gap. `NullEmbeddingIndexPort` is the only implementation as of Phase
12: no embeddings are computed, matching this phase's explicit "do not
implement embeddings yet."
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from jarvis.core.memory.types import ConversationTurn, MemoryQuery, MemoryRecord


@runtime_checkable
class MemoryManagerPort(Protocol):
    def remember_turn(self, session_id: str, turn: ConversationTurn) -> MemoryRecord:
        """Store one conversation exchange as ephemeral working memory
        (temporary=True by default) — this is the raw material recall()
        draws on and forget() clears.
        """
        ...

    def store_knowledge(
        self,
        content: str,
        *,
        session_id: str | None = None,
        importance: float = 0.6,
        tags: tuple[str, ...] = (),
        temporary: bool = False,
    ) -> MemoryRecord:
        """Explicitly store a fact/preference worth keeping — durable
        (temporary=False) by default, unlike remember_turn().
        """
        ...

    def recall(self, query: MemoryQuery) -> list[MemoryRecord]:
        """Return up to `query.limit` records relevant to `query.text`,
        ranked by importance/recency/keyword-overlap (ranking.py) —
        this is where "retrieve relevant memories" and "rank memory
        importance" both happen.
        """
        ...

    def get_by_ids(self, record_ids: list[int]) -> list[MemoryRecord]:
        """Fetch specific records by id, unranked. Used by
        hybrid_search.py to resolve a semantic-only hit (one
        EmbeddingIndexPort.search() found but recall()'s keyword
        candidate set didn't include) back into a full MemoryRecord.
        """
        ...

    def summarize_session(self, session_id: str) -> str:
        """Produce (and durably store, kind='summary') a short summary
        of a session's remembered turns. Deterministic/heuristic, not
        LLM-generated — see store.py's module docstring for why.
        """
        ...

    def forget(self, *, session_id: str | None = None, temporary_only: bool = True) -> int:
        """Delete matching records (temporary-only by default — durable
        knowledge/summaries survive unless temporary_only=False is
        passed explicitly). Returns the number of records deleted.
        """
        ...


@runtime_checkable
class EmbeddingIndexPort(Protocol):
    """Reserved for future semantic memory. No implementation computes
    real embeddings yet — see NullEmbeddingIndexPort.
    """

    def embed(self, text: str) -> list[float]: ...

    def index(self, record_id: int, vector: list[float]) -> None: ...

    def search(self, vector: list[float], *, limit: int = 5) -> list[tuple[int, float]]: ...


class NullEmbeddingIndexPort:
    """No embedding backend exists yet. embed() returns an empty
    vector, index() is a no-op, search() finds nothing — the correct
    behavior until a real embedding model is chosen.
    """

    def embed(self, text: str) -> list[float]:
        return []

    def index(self, record_id: int, vector: list[float]) -> None:
        pass

    def search(self, vector: list[float], *, limit: int = 5) -> list[tuple[int, float]]:
        return []
