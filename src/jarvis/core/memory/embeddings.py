"""EmbeddingProvider: text -> vector, for semantic memory (Phase 14).

`HashingEmbeddingProvider` is a real, working implementation — but a
deliberately lightweight one: it hashes each token into a fixed-size
bucket (the classic "feature hashing" / hashing trick) and L2-normalizes
the result, rather than calling a trained neural embedding model. This
was chosen over adding a real embedding model (sentence-transformers or
similar) for the same reason lightweight defaults were chosen
elsewhere in this project: zero new dependencies, fully deterministic,
instant, and testable with no download/GPU/network required. It
captures word-overlap similarity (two notes sharing vocabulary score
as "similar"), not true semantic/synonym understanding — that's the
honest limit of this approach, and exactly why `EmbeddingProvider` is a
Protocol: swapping in a real model later (lazy-imported, same pattern
as core/speech/'s backends) means implementing this one interface, not
restructuring `SemanticIndex` or `HybridMemorySearch`.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol, runtime_checkable

_TOKEN_RE = re.compile(r"[a-z0-9]+")


@runtime_checkable
class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> list[float]: ...


class HashingEmbeddingProvider:
    """Implements EmbeddingProvider via feature hashing."""

    def __init__(self, dim: int = 256) -> None:
        if dim <= 0:
            raise ValueError(f"dim must be positive, got {dim}")
        self._dim = dim

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self._dim
        tokens = _TOKEN_RE.findall(text.lower())
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], "big") % self._dim
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign
        return _normalize(vector)


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0.0:
        return vector
    return [v / norm for v in vector]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)
