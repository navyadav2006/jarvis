from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core.config.filesystem_config import FilesystemConfig
from jarvis.core.events import EventBus
from jarvis.core.filesystem.service import LocalFilesystemService


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def allowed_dir(root: Path) -> Path:
    directory = root / "allowed"
    directory.mkdir()
    return directory


@pytest.fixture
def fs_config() -> FilesystemConfig:
    return FilesystemConfig(
        allowed_dirs=[Path("allowed")],
        blacklisted_dirs=[],
        require_confirmation=["delete", "move", "rename"],
    )


@pytest.fixture
def fs_events() -> EventBus:
    return EventBus()


@pytest.fixture
def service(fs_config: FilesystemConfig, root: Path, fs_events: EventBus) -> LocalFilesystemService:
    return LocalFilesystemService(fs_config, root=root, events=fs_events)
