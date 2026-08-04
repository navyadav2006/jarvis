from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from jarvis.core.config.filesystem_config import FilesystemConfig
from jarvis.core.config.vault_config import VaultConfig
from jarvis.core.exceptions import NoteNotFoundError, VersionNotFoundError
from jarvis.core.filesystem import LocalFilesystemService
from jarvis.core.vault.service import VaultService


@pytest.fixture
def vault(tmp_path: Path) -> VaultService:
    filesystem = LocalFilesystemService(FilesystemConfig(allowed_dirs=[tmp_path]))
    config = VaultConfig(vault_dir=tmp_path / "vault", min_turns_for_auto_capture=3)
    return VaultService(filesystem, config)


def test_write_then_read_round_trips(vault: VaultService) -> None:
    vault.write_note("Notes/One.md", "hello world", frontmatter={"title": "One"})
    note = vault.read_note("Notes/One.md")
    assert note.body == "hello world"
    assert note.frontmatter["title"] == "One"
    assert "created" in note.frontmatter and "updated" in note.frontmatter


def test_read_missing_note_raises(vault: VaultService) -> None:
    with pytest.raises(NoteNotFoundError):
        vault.read_note("Notes/Missing.md")


def test_update_note_versions_the_previous_content(vault: VaultService) -> None:
    vault.write_note("Notes/One.md", "version 1")
    vault.update_note("Notes/One.md", "version 2")

    versions = vault.list_versions("Notes/One.md")
    assert len(versions) == 1
    assert "version 1" in versions[0].content
    assert vault.read_note("Notes/One.md").body == "version 2"


def test_first_write_creates_no_version(vault: VaultService) -> None:
    vault.write_note("Notes/One.md", "version 1")
    assert vault.list_versions("Notes/One.md") == []


def test_update_preserves_created_and_bumps_updated(vault: VaultService) -> None:
    vault.write_note("Notes/One.md", "v1", frontmatter={"title": "One"})
    created = vault.read_note("Notes/One.md").frontmatter["created"]

    vault.update_note("Notes/One.md", "v2")
    note = vault.read_note("Notes/One.md")

    assert note.frontmatter["created"] == created
    assert note.frontmatter["updated"] != created


def test_rollback_restores_prior_content_and_versions_current_state(vault: VaultService) -> None:
    vault.write_note("Notes/One.md", "version 1")
    vault.update_note("Notes/One.md", "version 2")
    [v1] = vault.list_versions("Notes/One.md")

    rolled_back = vault.rollback_note("Notes/One.md", v1.version_id)

    assert rolled_back.body == "version 1"
    assert vault.read_note("Notes/One.md").body == "version 1"
    # rollback itself is a versioned write — "version 2" is now recoverable too
    versions_after = vault.list_versions("Notes/One.md")
    assert len(versions_after) == 2


def test_rollback_unknown_version_raises(vault: VaultService) -> None:
    vault.write_note("Notes/One.md", "v1")
    with pytest.raises(VersionNotFoundError):
        vault.rollback_note("Notes/One.md", "does-not-exist")


def test_backlink_added_when_target_note_exists(vault: VaultService) -> None:
    vault.write_note("Notes/Bar.md", "bar content")
    vault.write_note("Notes/Foo.md", "links to [[Bar]]")

    bar = vault.read_note("Notes/Bar.md")
    assert "## Backlinks" in bar.body
    assert "[[Foo]]" in bar.body


def test_backlink_skipped_when_target_note_does_not_exist(vault: VaultService) -> None:
    vault.write_note("Notes/Foo.md", "links to [[Nonexistent]]")  # must not raise
    with pytest.raises(NoteNotFoundError):
        vault.read_note("Notes/Nonexistent.md")


def test_append_to_daily_journal_creates_then_appends(vault: VaultService) -> None:
    vault.append_to_daily_journal("first entry")
    vault.append_to_daily_journal("second entry")

    today_path = f"Daily/{date.today().isoformat()}.md"
    note = vault.read_note(today_path)
    assert "first entry" in note.body
    assert "second entry" in note.body
    assert note.frontmatter["type"] == "daily"


def test_create_project_note_sets_frontmatter(vault: VaultService) -> None:
    note = vault.create_project_note("Jarvis", "project body")
    assert note.frontmatter["type"] == "project"
    assert note.frontmatter["project"] == "Jarvis"
    assert vault.read_note("Projects/Jarvis.md").body == "project body"


def test_conversation_summary_below_threshold_is_skipped(vault: VaultService) -> None:
    result = vault.record_conversation_summary("s1", "summary", turn_count=1)
    assert result is None


def test_conversation_summary_above_threshold_is_written(vault: VaultService) -> None:
    result = vault.record_conversation_summary("s1", "summary text", turn_count=5)
    assert result is not None
    assert result.frontmatter["session_id"] == "s1"
    assert result.frontmatter["turn_count"] == 5


def test_record_devlog_slugifies_title(vault: VaultService) -> None:
    note = vault.record_devlog("My Big Feature!", "body")
    assert note.path == f"Devlogs/{date.today().isoformat()}-my-big-feature.md"


def test_list_notes_returns_all_notes_excluding_versions(vault: VaultService) -> None:
    vault.write_note("Notes/A.md", "a")
    vault.write_note("Projects/B.md", "b")
    vault.update_note("Notes/A.md", "a updated")  # creates a version snapshot

    notes = vault.list_notes()

    assert notes == ["Notes/A.md", "Projects/B.md"]
