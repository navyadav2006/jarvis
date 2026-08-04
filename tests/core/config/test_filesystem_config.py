from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from jarvis.core.config.filesystem_config import FilesystemConfig


def test_defaults() -> None:
    config = FilesystemConfig()
    assert config.allowed_dirs == [Path("data"), Path("vault")]
    assert config.blacklisted_dirs == []
    assert config.require_confirmation == ["delete", "move", "rename"]
    assert config.max_read_bytes == 10_000_000
    assert config.max_search_results == 1000


def test_is_frozen() -> None:
    config = FilesystemConfig()
    with pytest.raises(ValidationError):
        config.allowed_dirs = []  # type: ignore[misc]


def test_max_read_bytes_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        FilesystemConfig(max_read_bytes=0)


def test_max_search_results_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        FilesystemConfig(max_search_results=0)


def test_custom_allowed_and_blacklisted_dirs_round_trip() -> None:
    config = FilesystemConfig.model_validate(
        {"allowed_dirs": ["notes"], "blacklisted_dirs": ["notes/private"]}
    )
    assert config.allowed_dirs == [Path("notes")]
    assert config.blacklisted_dirs == [Path("notes/private")]
