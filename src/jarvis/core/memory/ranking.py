"""Pure-function memory ranking: importance + recency + keyword overlap.

No embeddings, no external dependencies — deliberately simple so it's
fully deterministic and testable, and easy to replace/augment once
EmbeddingIndexPort (ports.py) gets a real implementation (its `search()`
results would become a fourth term here, not a replacement for these
three).
"""

from __future__ import annotations

from datetime import UTC, datetime

from jarvis.core.memory.types import MemoryRecord

# (importance, keyword_overlap, recency) — importance weighted highest
# since it's the one signal a caller explicitly assigned on purpose.
_DEFAULT_WEIGHTS = (0.5, 0.3, 0.2)
_RECENCY_HALF_LIFE_HOURS = 24.0


def _keyword_overlap(query_text: str, content: str) -> float:
    query_words = {w for w in query_text.lower().split() if w}
    if not query_words:
        return 0.0
    content_words = {w for w in content.lower().split() if w}
    return len(query_words & content_words) / len(query_words)


def _recency_score(created_at: datetime, *, now: datetime) -> float:
    age_hours = max(0.0, (now - created_at).total_seconds() / 3600)
    return 0.5 ** (age_hours / _RECENCY_HALF_LIFE_HOURS)


def score_record(
    record: MemoryRecord,
    query_text: str,
    *,
    now: datetime | None = None,
    weights: tuple[float, float, float] = _DEFAULT_WEIGHTS,
) -> float:
    now = now or datetime.now(UTC)
    w_importance, w_keyword, w_recency = weights
    return (
        w_importance * record.importance
        + w_keyword * _keyword_overlap(query_text, record.content)
        + w_recency * _recency_score(record.created_at, now=now)
    )


def rank_records(
    records: list[MemoryRecord],
    query_text: str,
    *,
    now: datetime | None = None,
    weights: tuple[float, float, float] = _DEFAULT_WEIGHTS,
) -> list[MemoryRecord]:
    """Highest-scoring records first."""
    now = now or datetime.now(UTC)
    return sorted(
        records, key=lambda r: score_record(r, query_text, now=now, weights=weights), reverse=True
    )
