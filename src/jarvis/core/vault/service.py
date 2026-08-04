"""VaultService: a real VaultPort implementation over the existing
FilesystemPort (Phase 4) — reusing its allowlist/blacklist enforcement
(PathGuard already protects `vault/` by default) rather than touching
disk directly. This phase's whole purpose is a working Obsidian
integration, the same "real implementation, no Null default needed"
precedent as LocalFilesystemService/SqliteMemoryManager.

Version history and rollback: `update_note()` (and everything that
delegates to it — write_note(), append_to_daily_journal(), etc.) always
snapshots a note's current content to `versions_dir` *before*
overwriting it, whenever the note already exists. "Never overwrite
notes without version history" is therefore structural, not a
convention callers must remember — there is no code path in this class
that calls `filesystem.write()` on an existing note without versioning
it first. rollback_note() is a normal versioned write too (restoring
old content), so a rollback is itself always reversible.

Backlinks: intentionally simple — a `[[Target]]` wikilink in a note's
body triggers a search for `Target.md` anywhere in the vault; if found,
that note gets a "## Backlinks" entry pointing back. Notes that don't
exist yet are never auto-created as a side effect of linking to them
(Obsidian's own "create on click" behavior is a user action, not
something this phase reproduces).
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, date, datetime
from pathlib import Path

from jarvis.core.config.vault_config import VaultConfig
from jarvis.core.exceptions import (
    FilesystemOperationError,
    NoteNotFoundError,
    VersionNotFoundError,
)
from jarvis.core.filesystem.port import FilesystemPort
from jarvis.core.vault.backlinks import add_backlink, extract_links
from jarvis.core.vault.frontmatter import parse_frontmatter, render_frontmatter
from jarvis.core.vault.types import Note, NoteVersion

logger = logging.getLogger(__name__)

_VERSION_ID_FORMAT = "%Y%m%dT%H%M%S%f"


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "untitled"


class VaultService:
    """Implements core.vault.ports.VaultPort."""

    def __init__(self, filesystem: FilesystemPort, config: VaultConfig) -> None:
        self._filesystem = filesystem
        self._config = config

    # -- read/write/update ---------------------------------------------------

    def read_note(self, path: str) -> Note:
        text = self._read_raw(self._note_path(path))
        if text is None:
            raise NoteNotFoundError(f"no note at {path!r}")
        frontmatter, body = parse_frontmatter(text)
        return Note(path=path, frontmatter=frontmatter, body=body)

    def write_note(self, path: str, body: str, *, frontmatter: dict | None = None) -> Note:
        return self.update_note(path, body, frontmatter=frontmatter)

    def update_note(self, path: str, body: str, *, frontmatter: dict | None = None) -> Note:
        now = datetime.now(UTC).isoformat()
        try:
            existing = self.read_note(path)
            merged = dict(existing.frontmatter)
        except NoteNotFoundError:
            merged = {"created": now}
        merged.update(frontmatter or {})
        merged.setdefault("created", now)
        merged["updated"] = now

        text = render_frontmatter(merged, body)
        self._versioned_write(path, text)
        self._apply_backlinks(path, body)
        return Note(path=path, frontmatter=merged, body=body)

    def rollback_note(self, path: str, version_id: str) -> Note:
        content = self._read_raw(self._version_path(path, version_id))
        if content is None:
            raise VersionNotFoundError(f"no version {version_id!r} for note {path!r}")
        self._versioned_write(path, content)  # snapshots the pre-rollback state too
        frontmatter, body = parse_frontmatter(content)
        return Note(path=path, frontmatter=frontmatter, body=body)

    def list_versions(self, path: str) -> list[NoteVersion]:
        version_dir = f"{self._config.vault_dir}/{self._config.versions_dir}/{path}"
        try:
            matches = self._filesystem.search(version_dir, "*.md", recursive=False)
        except FilesystemOperationError:
            return []
        versions = []
        for match in matches:
            version_id = match.stem
            content = self._read_raw(str(match))
            if content is None:
                continue
            versions.append(NoteVersion(note_path=path, version_id=version_id, content=content))
        return sorted(versions, key=lambda v: v.version_id)

    def list_notes(self) -> list[str]:
        """Every note's vault-relative path — used by
        core/memory/vault_indexer.py to index the whole vault. Excludes
        version-history snapshots (`versions_dir`), which are not notes.
        """
        try:
            matches = self._filesystem.search(str(self._config.vault_dir), "*.md")
        except FilesystemOperationError:
            return []
        paths = [self._to_vault_relative(match) for match in matches]
        return sorted(p for p in paths if p is not None)

    # -- folder-organized convenience methods --------------------------------

    def append_to_daily_journal(self, text: str) -> Note:
        path = f"{self._config.daily_dir}/{date.today().isoformat()}.md"
        try:
            existing = self.read_note(path)
            new_body = existing.body.rstrip("\n") + "\n\n" + text
        except NoteNotFoundError:
            new_body = text
        return self.update_note(path, new_body, frontmatter={"type": "daily"})

    def create_project_note(
        self, project_name: str, body: str, *, frontmatter: dict | None = None
    ) -> Note:
        path = f"{self._config.projects_dir}/{project_name}.md"
        merged = {"type": "project", "project": project_name}
        merged.update(frontmatter or {})
        return self.update_note(path, body, frontmatter=merged)

    def record_conversation_summary(
        self, session_id: str, summary: str, *, turn_count: int
    ) -> Note | None:
        if turn_count < self._config.min_turns_for_auto_capture:
            logger.debug(
                "Skipping auto-capture for session %s (%d turn(s) < min %d)",
                session_id,
                turn_count,
                self._config.min_turns_for_auto_capture,
            )
            return None
        path = f"{self._config.conversations_dir}/{session_id}-{date.today().isoformat()}.md"
        return self.update_note(
            path,
            summary,
            frontmatter={
                "type": "conversation-summary",
                "session_id": session_id,
                "turn_count": turn_count,
            },
        )

    def record_devlog(self, title: str, body: str) -> Note:
        path = f"{self._config.devlogs_dir}/{date.today().isoformat()}-{_slugify(title)}.md"
        return self.update_note(path, body, frontmatter={"type": "devlog", "title": title})

    # -- internals ------------------------------------------------------------

    def _note_path(self, path: str) -> str:
        return f"{self._config.vault_dir}/{path}"

    def _version_path(self, path: str, version_id: str) -> str:
        # versions_dir nests *under* vault_dir (not a sibling of it) so
        # it stays inside the same allowlisted directory PathGuard
        # already grants access to — see filesystem.yaml's `allowed_dirs`.
        return f"{self._config.vault_dir}/{self._config.versions_dir}/{path}/{version_id}.md"

    def _read_raw(self, path: str) -> str | None:
        try:
            return self._filesystem.read(path)
        except FilesystemOperationError:
            return None

    def _versioned_write(self, path: str, new_text: str) -> None:
        existing = self._read_raw(self._note_path(path))
        if existing is not None:
            version_id = datetime.now(UTC).strftime(_VERSION_ID_FORMAT)
            self._filesystem.write(self._version_path(path, version_id), existing)
        self._filesystem.write(self._note_path(path), new_text)

    def _apply_backlinks(self, path: str, body: str) -> None:
        note_name = path.rsplit("/", 1)[-1].removesuffix(".md")
        for target in extract_links(body):
            if target == note_name:
                continue
            target_path = self._find_note_path(target)
            if target_path is None:
                continue
            try:
                target_note = self.read_note(target_path)
            except NoteNotFoundError:
                continue
            new_body = add_backlink(target_note.body, from_note=note_name)
            if new_body != target_note.body:
                self.update_note(target_path, new_body, frontmatter=target_note.frontmatter)

    def _find_note_path(self, note_name: str) -> str | None:
        try:
            matches = self._filesystem.search(str(self._config.vault_dir), f"{note_name}.md")
        except FilesystemOperationError:
            return None
        for match in matches:
            relative = self._to_vault_relative(match)
            if relative is not None:
                return relative
        return None

    def _to_vault_relative(self, match: Path) -> str | None:
        """A filesystem search result -> vault-relative note path, or
        None if it's not a note at all (e.g. a version-history
        snapshot). Centralized here because comparing a resolved
        `Path` against a POSIX search result is exactly the kind of
        string-matching code that's easy to get subtly wrong once and
        then wrong twice — see docs/architecture.md's Phase 13 section.
        """
        versions_root = self._config.versions_dir.parts[0]  # e.g. ".jarvis"
        if versions_root in match.parts:
            return None
        vault_root = self._config.vault_dir.as_posix()
        match_str = match.as_posix()
        idx = match_str.find(vault_root)
        if idx == -1:
            return None
        return match_str[idx + len(vault_root) :].lstrip("/")
