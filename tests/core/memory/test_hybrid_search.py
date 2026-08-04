from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core.config.memory_config import LongTermMemoryConfig
from jarvis.core.memory.embeddings import HashingEmbeddingProvider
from jarvis.core.memory.hybrid_search import HybridMemorySearch
from jarvis.core.memory.semantic_index import SemanticIndex
from jarvis.core.memory.store import SqliteMemoryManager


@pytest.fixture
def search(tmp_path: Path) -> HybridMemorySearch:
    memory = SqliteMemoryManager(LongTermMemoryConfig(database_path=tmp_path / "memory.db"))
    provider = HashingEmbeddingProvider(dim=64)
    semantic = SemanticIndex(
        provider, cache_path=tmp_path / "cache.json", index_path=tmp_path / "index.json"
    )

    for content, tag in [
        ("cats are independent pets that sleep a lot", "cats"),
        ("dogs are loyal companions that enjoy walks", "dogs"),
        ("electric cars use batteries instead of gasoline", "cars"),
    ]:
        record = memory.store_knowledge(content, tags=(f"vault:Notes/{tag}.md",))
        semantic.index(record.id, semantic.embed(content))

    return HybridMemorySearch(memory=memory, semantic_index=semantic, provider=provider)


def test_search_ranks_relevant_note_first(search: HybridMemorySearch) -> None:
    results = search.search("tell me about pets that sleep", limit=3)
    assert results[0].citation == "Notes/cats.md"


def test_search_returns_matched_via_labels(search: HybridMemorySearch) -> None:
    results = search.search("pets", limit=3)
    assert all(r.matched_via in ("keyword", "semantic", "both") for r in results)


def test_search_respects_limit(search: HybridMemorySearch) -> None:
    assert len(search.search("anything", limit=1)) == 1


def test_relevant_memories_returns_json_safe_dicts(search: HybridMemorySearch) -> None:
    memories = search.relevant_memories("dogs and walks", limit=2)
    assert len(memories) <= 2
    for m in memories:
        assert set(m.keys()) == {"content", "citation", "score", "matched_via"}
        assert isinstance(m["score"], float)


def test_citation_falls_back_to_kind_and_id_without_vault_tag(tmp_path: Path) -> None:
    memory = SqliteMemoryManager(LongTermMemoryConfig(database_path=tmp_path / "m.db"))
    provider = HashingEmbeddingProvider(dim=16)
    semantic = SemanticIndex(
        provider, cache_path=tmp_path / "c.json", index_path=tmp_path / "i.json"
    )
    record = memory.store_knowledge("no vault tag here")
    semantic.index(record.id, semantic.embed("no vault tag here"))

    search = HybridMemorySearch(memory=memory, semantic_index=semantic, provider=provider)
    results = search.search("no vault tag here", limit=1)

    assert results[0].citation == f"fact#{record.id}"
