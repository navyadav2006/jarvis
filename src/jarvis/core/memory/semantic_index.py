"""SemanticIndex: the first real implementation of Phase 12's
`EmbeddingIndexPort`, backed by a JSON file (stdlib `json`, no new
dependency — same reasoning as SqliteMemoryManager choosing stdlib
`sqlite3` over a new database dependency).

Two separate caches live in this one file:

  - content-hash -> vector ("the embedding cache" requirement):
    embed() is content-addressed, so re-indexing an unchanged note
    never recomputes its vector, regardless of which record_id it ends
    up stored under.
  - record_id -> vector (the actual searchable index): what search()
    scans. A vector only ever gets here via index(), separately from
    computing it via embed() — matching EmbeddingIndexPort's contract
    that the two are distinct steps.

`search()` is a linear cosine-similarity scan — appropriate for a
single vault's worth of notes (hundreds to low thousands), not a
production-scale ANN index. That trade-off is what `VectorIndexConfig`
(Phase 3, still reserved and untouched) is for: swapping in a real
FAISS-backed EmbeddingIndexPort later is a drop-in replacement for this
class, not a redesign of anything that calls it.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from pathlib import Path

from jarvis.core.memory.embeddings import EmbeddingProvider, cosine_similarity

logger = logging.getLogger(__name__)


class SemanticIndex:
    """Implements core.memory.ports.EmbeddingIndexPort."""

    def __init__(self, provider: EmbeddingProvider, *, cache_path: Path, index_path: Path) -> None:
        self._provider = provider
        self._cache_path = Path(cache_path)
        self._index_path = Path(index_path)
        self._lock = threading.Lock()
        self._cache: dict[str, list[float]] = self._load(self._cache_path)
        self._vectors: dict[str, list[float]] = self._load(self._index_path)

    def embed(self, text: str) -> list[float]:
        key = hashlib.sha256(text.encode("utf-8")).hexdigest()
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                return cached
            vector = self._provider.embed(text)
            self._cache[key] = vector
            self._save(self._cache_path, self._cache)
        return vector

    def index(self, record_id: int, vector: list[float]) -> None:
        with self._lock:
            self._vectors[str(record_id)] = vector
            self._save(self._index_path, self._vectors)

    def remove(self, record_id: int) -> None:
        with self._lock:
            if str(record_id) in self._vectors:
                del self._vectors[str(record_id)]
                self._save(self._index_path, self._vectors)

    def search(self, vector: list[float], *, limit: int = 5) -> list[tuple[int, float]]:
        with self._lock:
            items = list(self._vectors.items())
        scored = [(int(record_id), cosine_similarity(vector, v)) for record_id, v in items]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:limit]

    # -- internals ---------------------------------------------------------

    @staticmethod
    def _load(path: Path) -> dict[str, list[float]]:
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("Could not read %s; starting with an empty index", path)
            return {}

    @staticmethod
    def _save(path: Path, data: dict[str, list[float]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
