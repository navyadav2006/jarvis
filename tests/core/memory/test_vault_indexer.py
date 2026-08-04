from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core.config.filesystem_config import FilesystemConfig
from jarvis.core.config.memory_config import LongTermMemoryConfig
from jarvis.core.config.vault_config import VaultConfig
from jarvis.core.filesystem import LocalFilesystemService
from jarvis.core.memory.embeddings import HashingEmbeddingProvider
from jarvis.core.memory.semantic_index import SemanticIndex
from jarvis.core.memory.store import SqliteMemoryManager
from jarvis.core.memory.types import MemoryQuery
from jarvis.core.memory.vault_indexer import VaultIndexer
from jarvis.core.vault.service import VaultService


@pytest.fixture
def setup(tmp_path: Path):
    filesystem = LocalFilesystemService(FilesystemConfig(allowed_dirs=[tmp_path]))
    vault = VaultService(filesystem, VaultConfig(vault_dir=tmp_path / "vault"))
    memory = SqliteMemoryManager(LongTermMemoryConfig(database_path=tmp_path / "memory.db"))
    provider = HashingEmbeddingProvider(dim=32)
    semantic = SemanticIndex(
        provider, cache_path=tmp_path / "cache.json", index_path=tmp_path / "index.json"
    )
    indexer = VaultIndexer(
        vault=vault, memory=memory, semantic_index=semantic, state_path=tmp_path / "state.json"
    )
    return vault, memory, semantic, indexer


def test_index_vault_indexes_every_note(setup) -> None:
    vault, memory, semantic, indexer = setup
    vault.write_note("Notes/A.md", "content about apples")
    vault.write_note("Notes/B.md", "content about bananas")

    report = indexer.index_vault()

    assert report.indexed == 2
    assert report.skipped == 0


def test_second_index_vault_run_skips_unchanged_notes(setup) -> None:
    vault, memory, semantic, indexer = setup
    vault.write_note("Notes/A.md", "content about apples")

    indexer.index_vault()
    report = indexer.index_vault()

    assert report.indexed == 0
    assert report.skipped == 1


def test_changing_a_note_causes_reindex(setup) -> None:
    vault, memory, semantic, indexer = setup
    vault.write_note("Notes/A.md", "original content")
    indexer.index_vault()

    vault.update_note("Notes/A.md", "changed content")
    report = indexer.index_vault()

    assert report.indexed == 1


def test_indexed_note_is_recallable_by_keyword(setup) -> None:
    vault, memory, semantic, indexer = setup
    vault.write_note("Notes/A.md", "the kitchen lights are broken")
    indexer.index_vault()

    results = memory.recall(MemoryQuery(text="kitchen lights", limit=5))
    assert any("kitchen lights" in r.content for r in results)


def test_indexed_note_is_searchable_semantically(setup) -> None:
    vault, memory, semantic, indexer = setup
    vault.write_note("Notes/A.md", "cats are independent pets")
    indexer.index_vault()

    records = memory.recall(MemoryQuery(text="cats", limit=5))
    record = records[0]
    vector = semantic.embed("cats are independent pets")
    hits = semantic.search(vector, limit=5)
    assert hits[0][0] == record.id
