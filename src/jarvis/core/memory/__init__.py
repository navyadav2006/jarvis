"""The memory module (Phase 12): a dedicated Memory Manager Jarvis
calls via a structured API — maintain long-term memory, retrieve
relevant memories, rank importance, summarize conversations, store
useful knowledge, forget temporary information.

`SqliteMemoryManager` is a real, working implementation (stdlib
`sqlite3`, no new dependency). `orchestrator/memory_adapter.py` bridges
this module's own types to `orchestrator.ports.MemoryPort`'s shape,
keeping `core/` free of any dependency on `orchestrator/`.

Phase 14 gives `EmbeddingIndexPort` (prepared, unimplemented since
Phase 12) its first real implementation: `SemanticIndex` (a
JSON-persisted, content-hash-cached vector store) plus
`HashingEmbeddingProvider` (a dependency-free feature-hashing
embedding — see embeddings.py's module docstring for why). `VaultIndexer`
indexes an Obsidian vault (Phase 13) into memory incrementally, and
`HybridMemorySearch` combines keyword recall with semantic search into
ranked, cited results Jarvis can inject into a Cowork request's context
(see core/cowork/workspace.py).
"""

from __future__ import annotations

from jarvis.core.memory.embeddings import (
    EmbeddingProvider,
    HashingEmbeddingProvider,
    cosine_similarity,
)
from jarvis.core.memory.hybrid_search import HybridMemorySearch, MemoryCitation
from jarvis.core.memory.ports import EmbeddingIndexPort, MemoryManagerPort, NullEmbeddingIndexPort
from jarvis.core.memory.ranking import rank_records, score_record
from jarvis.core.memory.semantic_index import SemanticIndex
from jarvis.core.memory.store import SqliteMemoryManager
from jarvis.core.memory.types import ConversationTurn, MemoryKind, MemoryQuery, MemoryRecord
from jarvis.core.memory.vault_indexer import IndexReport, VaultIndexer

__all__ = [
    "ConversationTurn",
    "EmbeddingIndexPort",
    "EmbeddingProvider",
    "HashingEmbeddingProvider",
    "HybridMemorySearch",
    "IndexReport",
    "MemoryCitation",
    "MemoryKind",
    "MemoryManagerPort",
    "MemoryQuery",
    "MemoryRecord",
    "NullEmbeddingIndexPort",
    "SemanticIndex",
    "SqliteMemoryManager",
    "VaultIndexer",
    "cosine_similarity",
    "rank_records",
    "score_record",
]
