from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from jarvis.core.security.audit import SecurityAuditTrail
from jarvis.core.security.types import SecurityAuditEntry


def _entry(**overrides) -> SecurityAuditEntry:
    defaults = dict(
        timestamp=datetime.now(UTC),
        category="clipboard",
        action="get",
        requested_by="cowork",
        level="read",
        allowed=True,
        reason="allowed",
        required_confirmation=False,
    )
    defaults.update(overrides)
    return SecurityAuditEntry(**defaults)


def test_record_appends_a_json_line(tmp_path: Path) -> None:
    trail = SecurityAuditTrail(tmp_path / "audit.jsonl")
    trail.record(_entry())
    trail.record(_entry(action="set"))

    rows = trail.read_all()
    assert len(rows) == 2
    assert rows[0]["action"] == "get"
    assert rows[1]["action"] == "set"


def test_read_all_on_missing_file_returns_empty(tmp_path: Path) -> None:
    trail = SecurityAuditTrail(tmp_path / "does_not_exist.jsonl")
    assert trail.read_all() == []


def test_creates_parent_directories(tmp_path: Path) -> None:
    trail = SecurityAuditTrail(tmp_path / "nested" / "dir" / "audit.jsonl")
    trail.record(_entry())
    assert (tmp_path / "nested" / "dir" / "audit.jsonl").exists()


def test_denied_entry_is_recorded_with_allowed_false(tmp_path: Path) -> None:
    trail = SecurityAuditTrail(tmp_path / "audit.jsonl")
    trail.record(_entry(allowed=False, reason="rate limit exceeded"))
    rows = trail.read_all()
    assert rows[0]["allowed"] is False
    assert rows[0]["reason"] == "rate limit exceeded"
