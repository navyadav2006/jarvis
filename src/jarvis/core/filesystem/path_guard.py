"""Enforces the filesystem module's access policy.

Every path — read or write target, copy/move source or destination,
a search's base directory, a rename's computed new name — goes
through `PathGuard.check()` before anything touches disk. The
precedence is fixed and always applied in this order:

    1. Protected system paths — hardcoded, never configurable, always
       denied. This is what makes "never edit Windows / Program Files /
       System32 / the registry" an actual guarantee rather than a
       config default someone could accidentally (or deliberately)
       relax.
    2. Blacklisted directories — from filesystem.yaml's
       `blacklisted_dirs`. An explicit deny, checked before the
       allowlist, so a blacklist entry always wins even if it's nested
       inside an otherwise-allowed directory.
    3. Allowed directories — from filesystem.yaml's `allowed_dirs`.
       This is an allowlist, not a denylist: anything not inside one
       of these is denied by default ("prevent access outside allowed
       directories").

This is the same "deny beats allow, most specific/hardcoded wins
first" shape as PermissionsConfig.is_allowed() from Phase 3, applied
here to filesystem paths specifically.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from jarvis.core.config.filesystem_config import FilesystemConfig
from jarvis.core.exceptions import FilesystemAccessError

logger = logging.getLogger(__name__)


def _protected_system_paths() -> tuple[Path, ...]:
    """Hardcoded, environment-aware locations that must never be
    writable by the filesystem module, regardless of any config.

    Read from environment variables (with sane fallbacks) rather than
    hardcoded drive letters, since %WINDIR%/%ProgramFiles% are not
    always C:\\ in every Windows install (custom install drives,
    Windows-on-ARM, etc.) — the goal is to protect the *real* system
    directories on this machine, not a guess at where they usually are.
    """
    windir = Path(os.environ.get("WINDIR") or os.environ.get("SystemRoot") or r"C:\Windows")
    program_files = Path(os.environ.get("ProgramFiles") or r"C:\Program Files")
    program_files_x86 = Path(os.environ.get("ProgramFiles(x86)") or r"C:\Program Files (x86)")
    return (
        windir,  # "Windows" — includes System32 and everything else under it
        windir / "System32",  # "System32" — explicit, per the module's requirements
        windir / "System32" / "config",  # "Registry" — the on-disk hive files live here
        program_files,  # "Program Files"
        program_files_x86,  # "Program Files (x86)"
    )


PROTECTED_SYSTEM_PATHS: tuple[Path, ...] = _protected_system_paths()


class PathGuard:
    def __init__(self, config: FilesystemConfig, *, root: Path) -> None:
        self._root = root
        self._allowed = [self._normalize_config_path(p) for p in config.allowed_dirs]
        self._blacklisted = [self._normalize_config_path(p) for p in config.blacklisted_dirs]

    def check(self, path: str | Path) -> Path:
        """Resolve `path` and enforce the access policy.

        Returns the resolved, absolute path if permitted; raises
        FilesystemAccessError otherwise. Only touches the filesystem to
        resolve the path (which does not require the path to exist) —
        safe to call on a write/copy/move *destination* that doesn't
        exist yet.
        """
        resolved = self._normalize_config_path(Path(path))

        for protected in PROTECTED_SYSTEM_PATHS:
            if resolved.is_relative_to(protected):
                raise FilesystemAccessError(
                    f"{resolved} is inside a protected system path ({protected}) "
                    "and can never be accessed by the filesystem module"
                )

        for blocked in self._blacklisted:
            if resolved.is_relative_to(blocked):
                raise FilesystemAccessError(
                    f"{resolved} is inside a blacklisted directory ({blocked})"
                )

        if not any(resolved.is_relative_to(allowed) for allowed in self._allowed):
            raise FilesystemAccessError(f"{resolved} is not inside any allowed directory")

        return resolved

    def _normalize_config_path(self, path: Path) -> Path:
        # Relative paths (both config-declared and caller-supplied targets)
        # resolve against `root`, never the process's current working
        # directory. Resolving against CWD would make the effective
        # target depend on wherever Jarvis happened to be launched from
        # — exactly the ambiguity a working-directory trick could exploit
        # to escape the intended directory.
        expanded = path.expanduser()
        absolute = expanded if expanded.is_absolute() else self._root / expanded
        return absolute.resolve()
