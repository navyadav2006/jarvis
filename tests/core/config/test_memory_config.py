from __future__ import annotations

import pytest
from pydantic import ValidationError

from jarvis.core.config.memory_config import (
    LongTermMemoryConfig,
    MemoryConfig,
    ShortTermMemoryConfig,
)


def test_long_term_memory_disabled_by_default() -> None:
    assert MemoryConfig().long_term.enabled is False


def test_short_term_max_turns_must_be_at_least_one() -> None:
    with pytest.raises(ValidationError):
        ShortTermMemoryConfig(max_turns=0)


def test_embedding_dim_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        LongTermMemoryConfig.model_validate({"vector_index": {"embedding_dim": 0}})


def test_recall_limit_must_be_at_least_one() -> None:
    with pytest.raises(ValidationError):
        LongTermMemoryConfig(recall_limit=0)


def test_unsupported_vector_backend_is_rejected() -> None:
    with pytest.raises(ValidationError):
        LongTermMemoryConfig.model_validate({"vector_index": {"backend": "pinecone"}})
