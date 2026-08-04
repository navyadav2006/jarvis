"""memory.yaml — short-term (in-conversation) and long-term
(SQLite + FAISS, not yet implemented) memory settings.

`short_term.max_turns` is the configuration source of truth for
`Session.max_history` (orchestrator/models.py); the orchestrator does
not yet read it (Session is still constructed with its own hardcoded
default) — wiring that up belongs to whichever phase gives the
orchestrator a reason to consult MemoryConfig, not this one, whose job
is only to define and validate the schema. See docs/architecture.md's
Phase 3 section.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MEMORY_FILENAME = "memory.yaml"


class ShortTermMemoryConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_turns: int = Field(50, ge=1)


class VectorIndexConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    backend: Literal["faiss"] = "faiss"
    index_path: Path = Path("data/memory/index.faiss")
    embedding_dim: int = Field(384, gt=0)


class LongTermMemoryConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    enabled: bool = False
    database_path: Path = Path("data/memory/jarvis.db")
    vector_index: VectorIndexConfig = Field(default_factory=VectorIndexConfig)
    recall_limit: int = Field(5, ge=1)


class SemanticMemoryConfig(BaseModel):
    """Phase 14's real (if deliberately lightweight) semantic memory —
    distinct from `VectorIndexConfig` above, which stays reserved for a
    real FAISS backend later. See core/memory/embeddings.py's module
    docstring for why a dependency-free hashing embedding was chosen
    over pulling in a real embedding model for this phase.
    """

    model_config = ConfigDict(frozen=True)

    enabled: bool = False
    embedding_dim: int = Field(256, gt=0)
    cache_path: Path = Path("data/memory/embedding_cache.json")
    index_path: Path = Path("data/memory/semantic_index.json")

    # How much weight semantic similarity gets versus keyword/importance/
    # recency (ranking.py) when combining the two into one hybrid score.
    semantic_weight: float = Field(0.4, ge=0.0, le=1.0)

    # Max memories injected into a single Cowork request's context.
    context_injection_limit: int = Field(5, ge=1)


class MemoryConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    short_term: ShortTermMemoryConfig = Field(default_factory=ShortTermMemoryConfig)
    long_term: LongTermMemoryConfig = Field(default_factory=LongTermMemoryConfig)
    semantic: SemanticMemoryConfig = Field(default_factory=SemanticMemoryConfig)
