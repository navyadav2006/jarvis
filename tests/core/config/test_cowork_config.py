from __future__ import annotations

import pytest
from pydantic import ValidationError

from jarvis.core.config.cowork_config import CoworkConfig


def test_disabled_by_default() -> None:
    assert CoworkConfig().enabled is False


def test_defaults() -> None:
    config = CoworkConfig()
    assert config.max_retries == 2
    assert config.timeout_seconds == 30.0
    assert config.api_key_env_var == "COWORK_API_KEY"


def test_timeout_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        CoworkConfig(timeout_seconds=0)


def test_max_retries_cannot_be_negative() -> None:
    with pytest.raises(ValidationError):
        CoworkConfig(max_retries=-1)


def test_max_retries_can_be_zero() -> None:
    assert CoworkConfig(max_retries=0).max_retries == 0


def test_confidence_threshold_within_range() -> None:
    with pytest.raises(ValidationError):
        CoworkConfig(min_confidence_for_local=1.5)


def test_is_frozen() -> None:
    config = CoworkConfig()
    with pytest.raises(ValidationError):
        config.enabled = True  # type: ignore[misc]
