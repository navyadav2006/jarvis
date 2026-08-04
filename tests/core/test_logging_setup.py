from __future__ import annotations

import logging
from pathlib import Path

import pytest

from jarvis.core.config.app_config import LoggingSettings
from jarvis.core.logging_setup import configure_logging, reset_logging_state_for_tests, set_level


@pytest.fixture(autouse=True)
def _reset_logging():
    yield
    reset_logging_state_for_tests()


def test_set_level_changes_jarvis_logger_level(tmp_path: Path) -> None:
    configure_logging(LoggingSettings(level="INFO", dir=Path("logs")), root=tmp_path)

    set_level("DEBUG")

    assert logging.getLogger("jarvis").level == logging.DEBUG


def test_set_level_is_case_insensitive(tmp_path: Path) -> None:
    configure_logging(LoggingSettings(level="INFO", dir=Path("logs")), root=tmp_path)

    set_level("warning")

    assert logging.getLogger("jarvis").level == logging.WARNING
