"""FilesystemPort: the abstract interface plugins use for filesystem
access, injected via CapabilityContext exactly like MemoryPort and
AutomationPort (see orchestrator/models.py, orchestrator/orchestrator.py).

Unlike MemoryPort/AutomationPort — which are Null Object stand-ins for
a backend a later phase will build — LocalFilesystemService is a
complete, real implementation: this phase's whole purpose is a working
filesystem module, not a schema for one. FilesystemPort still exists
as a Protocol (rather than plugins depending on LocalFilesystemService
directly) for the same reason every other port does: it's what lets a
plugin be tested against a fake, and lets the concrete implementation
change without touching plugin code or the orchestrator.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class FileOperationResult:
    """What every mutating filesystem operation returns on success."""

    operation: str
    success: bool
    path: Path
    destination: Path | None = None


@runtime_checkable
class FilesystemPort(Protocol):
    def read(self, path: str | Path) -> str:
        """Read a UTF-8 text file and return its contents."""
        ...

    def write(
        self, path: str | Path, content: str, *, confirmed: bool = False
    ) -> FileOperationResult:
        """Write UTF-8 text to `path`, creating parent directories as needed."""
        ...

    def copy(
        self, source: str | Path, destination: str | Path, *, confirmed: bool = False
    ) -> FileOperationResult:
        """Copy a file or directory tree from `source` to `destination`."""
        ...

    def move(
        self, source: str | Path, destination: str | Path, *, confirmed: bool = False
    ) -> FileOperationResult:
        """Move a file or directory from `source` to `destination`."""
        ...

    def rename(
        self, path: str | Path, new_name: str, *, confirmed: bool = False
    ) -> FileOperationResult:
        """Rename `path` in place to `new_name` (a filename, not a path)."""
        ...

    def delete(self, path: str | Path, *, confirmed: bool = False) -> FileOperationResult:
        """Delete a file, or a directory and everything under it."""
        ...

    def search(
        self, directory: str | Path, pattern: str, *, recursive: bool = True
    ) -> list[Path]:
        """Glob-search `directory` for `pattern`, returning matching paths."""
        ...
