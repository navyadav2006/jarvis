from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core.memory.embeddings import HashingEmbeddingProvider
from jarvis.core.memory.ports import EmbeddingIndexPort
from jarvis.core.memory.semantic_index import SemanticIndex


@pytest.fixture
def index(tmp_path: Path) -> SemanticIndex:
    provider = HashingEmbeddingProvider(dim=32)
    return SemanticIndex(
        provider, cache_path=tmp_path / "cache.json", index_path=tmp_path / "index.json"
    )


def test_satisfies_embedding_index_port(index: SemanticIndex) -> None:
    assert isinstance(index, EmbeddingIndexPort)


def test_embed_is_content_addressed_and_cached(index: SemanticIndex, tmp_path: Path) -> None:
    v1 = index.embed("hello world")
    assert (tmp_path / "cache.json").exists()
    v2 = index.embed("hello world")
    assert v1 == v2


class _CountingProvider:
    def __init__(self) -> None:
        self.calls = 0
        self._inner = HashingEmbeddingProvider(dim=16)

    def embed(self, text: str) -> list[float]:
        self.calls += 1
        return self._inner.embed(text)


def test_embed_cache_avoids_recomputation(tmp_path: Path) -> None:
    provider = _CountingProvider()
    index = SemanticIndex(
        provider, cache_path=tmp_path / "cache.json", index_path=tmp_path / "index.json"
    )
    index.embed("some content")
    index.embed("some content")
    assert provider.calls == 1


def test_index_then_search_finds_the_record(index: SemanticIndex) -> None:
    vector = index.embed("cats are great pets")
    index.index(1, vector)
    results = index.search(index.embed("cats are great pets"), limit=5)
    assert results[0][0] == 1
    assert results[0][1] == pytest.approx(1.0, abs=1e-9)


def test_search_respects_limit(index: SemanticIndex) -> None:
    for i in range(5):
        index.index(i, index.embed(f"text number {i}"))
    results = index.search(index.embed("text number 0"), limit=2)
    assert len(results) == 2


def test_remove_drops_a_record_from_search(index: SemanticIndex) -> None:
    vector = index.embed("something")
    index.index(1, vector)
    index.remove(1)
    assert index.search(vector, limit=5) == []


def test_index_and_cache_persist_across_instances(tmp_path: Path) -> None:
    provider = HashingEmbeddingProvider(dim=16)
    cache_path = tmp_path / "cache.json"
    index_path = tmp_path / "index.json"

    first = SemanticIndex(provider, cache_path=cache_path, index_path=index_path)
    vector = first.embed("persisted content")
    first.index(1, vector)

    second = SemanticIndex(provider, cache_path=cache_path, index_path=index_path)
    results = second.search(vector, limit=5)
    assert results[0][0] == 1


def test_corrupt_cache_file_is_ignored_not_fatal(tmp_path: Path) -> None:
    cache_path = tmp_path / "cache.json"
    cache_path.write_text("not valid json", encoding="utf-8")
    provider = HashingEmbeddingProvider(dim=16)
    index = SemanticIndex(provider, cache_path=cache_path, index_path=tmp_path / "index.json")
    assert index.embed("text") is not None  # must not raise
