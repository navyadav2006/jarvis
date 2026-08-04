"""VaultPort: the abstract interface for the Obsidian vault module —
same role FilesystemPort/MemoryManagerPort play for their modules.
`VaultService` (service.py) is the one real implementation this phase
delivers; `NullVaultPort` is the safe default for callers/tests that
don't have a vault configured, following every other module's Null
Object convention.
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from jarvis.core.exceptions import NoteNotFoundError, VersionNotFoundError
from jarvis.core.vault.types import Note, NoteVersion

logger = logging.getLogger(__name__)


@runtime_checkable
class VaultPort(Protocol):
    def read_note(self, path: str) -> Note: ...

    def list_notes(self) -> list[str]: ...

    def write_note(
        self, path: str, body: str, *, frontmatter: dict | None = None
    ) -> Note: ...

    def update_note(
        self, path: str, body: str, *, frontmatter: dict | None = None
    ) -> Note: ...

    def rollback_note(self, path: str, version_id: str) -> Note: ...

    def list_versions(self, path: str) -> list[NoteVersion]: ...

    def append_to_daily_journal(self, text: str) -> Note: ...

    def create_project_note(
        self, project_name: str, body: str, *, frontmatter: dict | None = None
    ) -> Note: ...

    def record_conversation_summary(
        self, session_id: str, summary: str, *, turn_count: int
    ) -> Note | None: ...

    def record_devlog(self, title: str, body: str) -> Note: ...


class NullVaultPort:
    """No vault configured. Reads raise NoteNotFoundError (there's
    nothing to find); writes are logged and discarded rather than
    silently succeeding with nothing durable behind them, mirroring
    NullAutomationPort's "report failure explicitly" convention rather
    than NullMemoryPort's "silently discard" one — a caller that writes
    a note and gets nothing back should be able to tell.
    """

    def read_note(self, path: str) -> Note:
        raise NoteNotFoundError(f"no vault backend configured; cannot read {path!r}")

    def list_notes(self) -> list[str]:
        return []

    def write_note(self, path: str, body: str, *, frontmatter: dict | None = None) -> Note:
        logger.warning("NullVaultPort.write_note(%r) — no vault backend configured", path)
        return Note(path=path, frontmatter=frontmatter or {}, body=body)

    def update_note(self, path: str, body: str, *, frontmatter: dict | None = None) -> Note:
        return self.write_note(path, body, frontmatter=frontmatter)

    def rollback_note(self, path: str, version_id: str) -> Note:
        raise VersionNotFoundError(f"no vault backend configured; cannot roll back {path!r}")

    def list_versions(self, path: str) -> list[NoteVersion]:
        return []

    def append_to_daily_journal(self, text: str) -> Note:
        return self.write_note("Daily/null.md", text)

    def create_project_note(
        self, project_name: str, body: str, *, frontmatter: dict | None = None
    ) -> Note:
        return self.write_note(f"Projects/{project_name}.md", body, frontmatter=frontmatter)

    def record_conversation_summary(
        self, session_id: str, summary: str, *, turn_count: int
    ) -> Note | None:
        return None

    def record_devlog(self, title: str, body: str) -> Note:
        return self.write_note(f"Devlogs/{title}.md", body)
