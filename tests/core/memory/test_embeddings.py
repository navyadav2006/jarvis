from __future__ import annotations

import pytest

from jarvis.core.memory.embeddings import HashingEmbeddingProvider, cosine_similarity


def test_embed_returns_a_unit_length_vector() -> None:
    provider = HashingEmbeddingProvider(dim=32)
    vector = provider.embed("cats are great pets")
    length = sum(v * v for v in vector) ** 0.5
    assert pytest.approx(length, abs=1e-9) == 1.0
    assert len(vector) == 32


def test_embed_is_deterministic() -> None:
    provider = HashingEmbeddingProvider(dim=32)
    assert provider.embed("hello world") == provider.embed("hello world")


def test_empty_text_returns_zero_vector() -> None:
    provider = HashingEmbeddingProvider(dim=16)
    assert provider.embed("") == [0.0] * 16


def test_invalid_dim_rejected() -> None:
    with pytest.raises(ValueError):
        HashingEmbeddingProvider(dim=0)


def test_similar_texts_score_higher_than_unrelated_ones() -> None:
    provider = HashingEmbeddingProvider(dim=128)
    cats_a = provider.embed("cats are independent pets that sleep a lot")
    cats_b = provider.embed("cats sleep most of the day and are independent")
    cars = provider.embed("electric cars use batteries instead of gasoline")

    sim_cats = cosine_similarity(cats_a, cats_b)
    sim_unrelated = cosine_similarity(cats_a, cars)
    assert sim_cats > sim_unrelated


def test_cosine_similarity_identical_vectors_is_one() -> None:
    provider = HashingEmbeddingProvider(dim=16)
    v = provider.embed("some text")
    assert pytest.approx(cosine_similarity(v, v), abs=1e-9) == 1.0


def test_cosine_similarity_mismatched_lengths_returns_zero() -> None:
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0, 0.0]) == 0.0


def test_cosine_similarity_zero_vector_returns_zero() -> None:
    assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0
