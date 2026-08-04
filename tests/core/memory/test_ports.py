from __future__ import annotations

from jarvis.core.memory.ports import EmbeddingIndexPort, NullEmbeddingIndexPort


def test_null_embedding_index_satisfies_protocol() -> None:
    assert isinstance(NullEmbeddingIndexPort(), EmbeddingIndexPort)


def test_null_embedding_index_returns_empty_results() -> None:
    port = NullEmbeddingIndexPort()
    assert port.embed("hello") == []
    assert port.search([0.1, 0.2], limit=5) == []
    port.index(1, [0.1, 0.2])  # must not raise
