from __future__ import annotations

from datetime import UTC, datetime, timedelta

from jarvis.core.memory.ranking import rank_records
from jarvis.core.memory.types import MemoryRecord

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _record(content: str, *, importance: float = 0.5, age_hours: float = 0.0) -> MemoryRecord:
    return MemoryRecord(
        id=None,
        content=content,
        kind="fact",
        session_id="s1",
        importance=importance,
        created_at=NOW - timedelta(hours=age_hours),
        last_accessed_at=None,
        temporary=False,
    )


def test_higher_importance_ranks_first_when_other_factors_equal() -> None:
    low = _record("apple", importance=0.1)
    high = _record("banana", importance=0.9)
    ranked = rank_records([low, high], "", now=NOW)
    assert ranked == [high, low]


def test_keyword_overlap_boosts_matching_content() -> None:
    matching = _record("the lights are in the kitchen", importance=0.3)
    unrelated = _record("the weather is sunny today", importance=0.3)
    ranked = rank_records([unrelated, matching], "kitchen lights", now=NOW)
    assert ranked[0] is matching


def test_recent_records_outrank_older_ones_at_equal_importance() -> None:
    recent = _record("recent note", importance=0.5, age_hours=0.0)
    old = _record("old note", importance=0.5, age_hours=200.0)
    ranked = rank_records([old, recent], "", now=NOW)
    assert ranked == [recent, old]


def test_empty_query_text_does_not_crash_on_keyword_scoring() -> None:
    record = _record("anything")
    assert rank_records([record], "", now=NOW) == [record]
