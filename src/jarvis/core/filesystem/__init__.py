"""The filesystem module: allowlist/blacklist-enforced, logged,
confirmation-gated file operations (copy/move/rename/delete/search/
read/write) — safe against path traversal, and hardcoded to never
touch Windows/Program Files/System32/the registry regardless of
config.

See docs/architecture.md's Phase 4 section for the full design
rationale: why paths resolve against the project root rather than the
process's current working directory, the fixed precedence order
(protected system paths > blacklist > allowlist), and why confirmation
is a caller-supplied flag rather than an interactive prompt.
"""

from __future__ import annotations

from jarvis.core.filesystem.path_guard import PROTECTED_SYSTEM_PATHS, PathGuard
from jarvis.core.filesystem.port import FileOperationResult, FilesystemPort
from jarvis.core.filesystem.service import LocalFilesystemService

__all__ = [
    "PROTECTED_SYSTEM_PATHS",
    "PathGuard",
    "FileOperationResult",
    "FilesystemPort",
    "LocalFilesystemService",
]
