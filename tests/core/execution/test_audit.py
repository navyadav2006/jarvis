from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from jarvis.core.execution.audit import AuditTrail
from jarvis.core.execution.types import AuditEntry


def _entry(**overrides) -> AuditEntry:
    defaults = dict(
        timestamp=datetime.now(UTC),
        category="filesystem",
        action="write",
        requested_by="cowork",
        parameters={"path": "x"},
        allowed=True,
        success=True,
        output="ok",
        error=None,
        duration_seconds=0.01,
    )
    defaults.update(overrides)
    return AuditEntry(**defaults)


def test_record_appends_a_json_line(tmp_path: Path) -> None:
    trail = AuditTrail(tmp_path / "audit.jsonl")
    trail.record(_entry())
    trail.record(_entry(action="read"))

    rows = trail.read_all()
    assert len(rows) == 2
    assert rows[0]["action"] == "write"
    assert rows[1]["action"] == "read"


def test_read_all_on_missing_file_returns_empty(tmp_path: Path) -> None:
    trail = AuditTrail(tmp_path / "does_not_exist.jsonl")
    assert trail.read_all() == []


def test_creates_parent_directories(tmp_path: Path) -> None:
    trail = AuditTrail(tmp_path / "nested" / "dir" / "audit.jsonl")
    trail.record(_entry())
    assert (tmp_path / "nested" / "dir" / "audit.jsonl").exists()


def test_denied_entry_is_recorded_with_allowed_false(tmp_path: Path) -> None:
    trail = AuditTrail(tmp_path / "audit.jsonl")
    trail.record(_entry(allowed=False, success=False, error="permission denied", output=None))
    rows = trail.read_all()
    assert rows[0]["allowed"] is False
    assert rows[0]["error"] == "permission denied"
