"""Logging configuration.

Every subsystem should log through ``logging.getLogger(__name__)`` as
usual; this module's only job is to configure the root ``jarvis`` logger
once, at startup, so all child loggers (``jarvis.core.plugin_loader``,
``jarvis.plugins.foo``, ...) inherit console + rotating-file handlers
and a consistent format.

Kept separate from config.py so that "what gets logged" (LoggingSettings)
stays decoupled from "how logging is wired up" (this module).
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from jarvis.core.config import PROJECT_ROOT, LoggingSettings

_LOGGER_NAME = "jarvis"
_configured = False


def configure_logging(settings: LoggingSettings, *, root: Path = PROJECT_ROOT) -> logging.Logger:
    """Configure and return the ``jarvis`` logger. Idempotent.

    Safe to call multiple times (e.g. once from main.py, once from a
    test fixture) — subsequent calls are no-ops so handlers are never
    duplicated.
    """
    global _configured
    logger = logging.getLogger(_LOGGER_NAME)

    if _configured:
        return logger

    logger.setLevel(settings.level.upper())
    logger.propagate = False

    formatter = logging.Formatter(fmt=settings.format, datefmt=settings.date_format)

    if settings.console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    log_dir = root / settings.dir
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / settings.file_name,
        maxBytes=settings.max_bytes,
        backupCount=settings.backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    _configured = True
    logger.debug("Logging configured (level=%s, console=%s)", settings.level, settings.console)
    return logger


def get_logger(name: str) -> logging.Logger:
    """Convenience wrapper: ``get_logger(__name__)`` in any module."""
    return logging.getLogger(name)


def set_level(level: str) -> None:
    """Update the running ``jarvis`` logger's level without touching handlers.

    Split out from configure_logging() specifically so a live-reloaded
    settings.yaml can change verbosity without a restart: main.py
    subscribes this to the "config.reloaded" event. Handlers (console,
    rotating file) are untouched — only the logger's level changes.
    """
    logging.getLogger(_LOGGER_NAME).setLevel(level.upper())
    logging.getLogger(__name__).info("Log level changed to %s", level.upper())


def reset_logging_state_for_tests() -> None:
    """Undo configure_logging()'s idempotency guard and remove handlers.

    Test-only. Without this, running configure_logging() in one test
    with a temp log dir would silently leak into later tests because
    the module-level _configured flag would already be True.
    """
    global _configured
    logger = logging.getLogger(_LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    _configured = False
