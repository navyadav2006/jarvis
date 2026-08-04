from __future__ import annotations

import pytest

from jarvis.core.exceptions import NoteNotFoundError, VersionNotFoundError
from jarvis.core.vault.ports import NullVaultPort, VaultPort


def test_null_vault_satisfies_protocol() -> None:
    assert isinstance(NullVaultPort(), VaultPort)


def test_null_vault_read_raises_note_not_found() -> None:
    with pytest.raises(NoteNotFoundError):
        NullVaultPort().read_note("anything.md")


def test_null_vault_write_returns_note_but_discards() -> None:
    note = NullVaultPort().write_note("x.md", "body")
    assert note.body == "body"


def test_null_vault_rollback_raises_version_not_found() -> None:
    with pytest.raises(VersionNotFoundError):
        NullVaultPort().rollback_note("x.md", "v1")


def test_null_vault_list_versions_returns_empty() -> None:
    assert NullVaultPort().list_versions("x.md") == []


def test_null_vault_list_notes_returns_empty() -> None:
    assert NullVaultPort().list_notes() == []


def test_null_vault_record_conversation_summary_returns_none() -> None:
    assert NullVaultPort().record_conversation_summary("s1", "text", turn_count=10) is None
