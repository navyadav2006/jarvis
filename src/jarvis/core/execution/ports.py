"""Category-handler interfaces for the Desktop Execution Engine.

Filesystem actions reuse the existing `FilesystemPort` (Phase 4)
directly — no new protocol needed. Terminal/application are real,
dependency-free implementations (stdlib `subprocess`, same "this phase
delivers a working thing" precedent as LocalFilesystemService).
Desktop/clipboard/screenshot/window each wrap an optional third-party
library, lazily imported, following core/speech/'s established pattern
— constructing any of these classes never requires the library to be
installed; only a real call does, and it fails with a clear
`ExecutionBackendUnavailableError` rather than a raw ImportError.

Every category has a Null Object default so `ExecutionEngine` can be
constructed with only the categories a deployment actually cares about
wired to something real — the rest safely refuse (not silently no-op,
since a caller commanding "click here" deserves to know nothing
happened, mirroring NullAutomationPort's "report failure explicitly"
convention from Phase 2).
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from jarvis.core.exceptions import ExecutionBackendUnavailableError

logger = logging.getLogger(__name__)


@runtime_checkable
class TerminalPort(Protocol):
    def run(self, command: str, args: list[str], *, timeout: float) -> tuple[int, str, str]:
        """Run `command` with `args`; returns (exit_code, stdout, stderr)."""
        ...


@runtime_checkable
class DesktopAutomationPort(Protocol):
    def click(self, x: int, y: int) -> None: ...
    def type_text(self, text: str) -> None: ...
    def key_press(self, key: str) -> None: ...


@runtime_checkable
class ApplicationPort(Protocol):
    def launch(self, path: str, args: list[str]) -> int:
        """Start `path` as a new process; returns its process id."""
        ...

    def close(self, process_name: str) -> bool:
        """Terminate every process named `process_name`. Returns
        whether anything was actually terminated.
        """
        ...


@runtime_checkable
class ClipboardPort(Protocol):
    def get(self) -> str: ...
    def set(self, text: str) -> None: ...


@runtime_checkable
class ScreenshotPort(Protocol):
    def capture(self, path: str) -> str:
        """Save a screenshot to `path`; returns the path actually written."""
        ...


@runtime_checkable
class WindowPort(Protocol):
    def list_windows(self) -> list[str]: ...
    def focus(self, title: str) -> bool: ...
    def minimize(self, title: str) -> bool: ...
    def maximize(self, title: str) -> bool: ...


class NullTerminalPort:
    def run(self, command: str, args: list[str], *, timeout: float) -> tuple[int, str, str]:
        raise ExecutionBackendUnavailableError("no terminal backend configured")


class NullDesktopAutomationPort:
    def click(self, x: int, y: int) -> None:
        raise ExecutionBackendUnavailableError("no desktop automation backend configured")

    def type_text(self, text: str) -> None:
        raise ExecutionBackendUnavailableError("no desktop automation backend configured")

    def key_press(self, key: str) -> None:
        raise ExecutionBackendUnavailableError("no desktop automation backend configured")


class NullApplicationPort:
    def launch(self, path: str, args: list[str]) -> int:
        raise ExecutionBackendUnavailableError("no application backend configured")

    def close(self, process_name: str) -> bool:
        raise ExecutionBackendUnavailableError("no application backend configured")


class NullClipboardPort:
    def get(self) -> str:
        raise ExecutionBackendUnavailableError("no clipboard backend configured")

    def set(self, text: str) -> None:
        raise ExecutionBackendUnavailableError("no clipboard backend configured")


class NullScreenshotPort:
    def capture(self, path: str) -> str:
        raise ExecutionBackendUnavailableError("no screenshot backend configured")


class NullWindowPort:
    def list_windows(self) -> list[str]:
        raise ExecutionBackendUnavailableError("no window backend configured")

    def focus(self, title: str) -> bool:
        raise ExecutionBackendUnavailableError("no window backend configured")

    def minimize(self, title: str) -> bool:
        raise ExecutionBackendUnavailableError("no window backend configured")

    def maximize(self, title: str) -> bool:
        raise ExecutionBackendUnavailableError("no window backend configured")
