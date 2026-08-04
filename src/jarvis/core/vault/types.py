"""Plain data types for the vault module.

Independent of orchestrator/'s Turn/Session (same "core never depends
on orchestrator" rule core/memory/types.py already follows) — a
conversation is passed in as plain strings, not an orchestrator type.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class Note:
    """A parsed note: YAML frontmatter plus Markdown body."""

    path: str  # vault-relative, forward-slash-separated
    frontmatter: dict[str, Any]
    body: str

    @property
    def title(self) -> str:
        return str(self.frontmatter.get("title", self.path))


@dataclass(frozen=True)
class NoteVersion:
    """One historical snapshot of a note, saved before it was
    overwritten — see service.py's update_note()/rollback_note().
    """

    note_path: str
    version_id: str  # ISO-8601 timestamp, also the version file's name
    content: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
