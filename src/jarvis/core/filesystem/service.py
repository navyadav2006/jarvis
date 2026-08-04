"""LocalFilesystemService: the real, working implementation of
FilesystemPort — copy/move/rename/delete/search/read/write, all
routed through PathGuard first and logged, with destructive operations
gated behind an explicit `confirmed=True`.

Every method funnels through `_prepare()` (path-policy enforcement +
logging) and, for operations named in `filesystem.yaml`'s
`require_confirmation` (delete/move/rename by default), through
`_require_confirmation()` before anything touches disk. Centralizing
both here — rather than each method remembering to call them — is what
makes "all operations are logged" and "destructive actions need
confirmation" structural guarantees of this class's shape rather than
a convention seven separate methods could each get slightly wrong.

Confirmation is a plain boolean the *caller* supplies, not an
interactive prompt this class shows itself: LocalFilesystemService has
no concept of a user or a UI, and no chat/voice loop exists yet to ask
"are you sure?" (see docs/architecture.md's Phase 4 section). A
capability handler that wants to actually confirm with the user is
expected to call once, catch ConfirmationRequiredError, surface that
to the user however its channel does that, and call again with
confirmed=True once they agree.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any, NoReturn

from jarvis.core.config._paths import PROJECT_ROOT
from jarvis.core.config.filesystem_config import FilesystemConfig
from jarvis.core.events import EventBus
from jarvis.core.exceptions import (
    ConfirmationRequiredError,
    FilesystemAccessError,
    FilesystemOperationError,
)
from jarvis.core.filesystem.path_guard import PathGuard
from jarvis.core.filesystem.port import FileOperationResult

logger = logging.getLogger(__name__)


class LocalFilesystemService:
    def __init__(
        self,
        config: FilesystemConfig,
        *,
        root: Path = PROJECT_ROOT,
        events: EventBus | None = None,
    ) -> None:
        self._config = config
        self._guard = PathGuard(config, root=root)
        self._events = events

    # -- read-only operations -------------------------------------------------

    def read(self, path: str | Path) -> str:
        resolved = self._prepare("read", path)
        try:
            size = resolved.stat().st_size
            if size > self._config.max_read_bytes:
                raise FilesystemOperationError(
                    f"{resolved} is {size} bytes, exceeds max_read_bytes "
                    f"({self._config.max_read_bytes})"
                )
            content = resolved.read_text(encoding="utf-8")
        except OSError as exc:
            self._fail("read", resolved, exc)
        self._succeed("read", resolved)
        return content

    def search(
        self, directory: str | Path, pattern: str, *, recursive: bool = True
    ) -> list[Path]:
        resolved = self._prepare("search", directory)
        matches: list[Path] = []
        try:
            candidates = resolved.rglob(pattern) if recursive else resolved.glob(pattern)
            for candidate in candidates:
                try:
                    matches.append(self._guard.check(candidate))
                except FilesystemAccessError:
                    # Defense in depth: a glob match should always be inside
                    # `resolved` already, but a symlink pointing outside the
                    # allowed tree could still surface here. Excluding it
                    # (rather than raising) lets a search keep working while
                    # never returning a path the caller isn't allowed to touch.
                    logger.warning(
                        "search match %s excluded: escapes allowed paths (possible symlink)",
                        candidate,
                    )
                    continue
                if len(matches) >= self._config.max_search_results:
                    break
        except OSError as exc:
            self._fail("search", resolved, exc)
        self._succeed("search", resolved, pattern=pattern, matches=len(matches))
        return matches

    # -- mutating operations ---------------------------------------------------

    def write(
        self, path: str | Path, content: str, *, confirmed: bool = False
    ) -> FileOperationResult:
        resolved = self._prepare("write", path)
        self._require_confirmation("write", confirmed)
        try:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(content, encoding="utf-8")
        except OSError as exc:
            self._fail("write", resolved, exc)
        self._succeed("write", resolved)
        return FileOperationResult(operation="write", success=True, path=resolved)

    def copy(
        self, source: str | Path, destination: str | Path, *, confirmed: bool = False
    ) -> FileOperationResult:
        src = self._prepare("copy", source)
        dst = self._prepare("copy", destination)
        self._require_confirmation("copy", confirmed)
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
        except OSError as exc:
            self._fail("copy", src, exc, destination=dst)
        self._succeed("copy", src, destination=dst)
        return FileOperationResult(operation="copy", success=True, path=src, destination=dst)

    def move(
        self, source: str | Path, destination: str | Path, *, confirmed: bool = False
    ) -> FileOperationResult:
        src = self._prepare("move", source)
        dst = self._prepare("move", destination)
        self._require_confirmation("move", confirmed)
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
        except OSError as exc:
            self._fail("move", src, exc, destination=dst)
        self._succeed("move", src, destination=dst)
        return FileOperationResult(operation="move", success=True, path=src, destination=dst)

    def rename(
        self, path: str | Path, new_name: str, *, confirmed: bool = False
    ) -> FileOperationResult:
        resolved = self._prepare("rename", path)
        if not new_name or new_name in {".", ".."} or "/" in new_name or "\\" in new_name:
            raise FilesystemOperationError(
                f"invalid new_name {new_name!r}: must be a single, non-empty filename"
            )
        # Re-checked through the guard, not just derived from an
        # already-permitted path: with_name() builds a sibling path that
        # PathGuard has never validated, so it goes through check() again
        # exactly like any other target — this is what stops a rename
        # from being used to hop into a blacklisted or protected sibling.
        destination = self._guard.check(resolved.with_name(new_name))
        self._require_confirmation("rename", confirmed)
        try:
            resolved.rename(destination)
        except OSError as exc:
            self._fail("rename", resolved, exc, destination=destination)
        self._succeed("rename", resolved, destination=destination)
        return FileOperationResult(
            operation="rename", success=True, path=resolved, destination=destination
        )

    def delete(self, path: str | Path, *, confirmed: bool = False) -> FileOperationResult:
        resolved = self._prepare("delete", path)
        self._require_confirmation("delete", confirmed)
        try:
            if resolved.is_dir():
                shutil.rmtree(resolved)
            else:
                resolved.unlink()
        except OSError as exc:
            self._fail("delete", resolved, exc)
        self._succeed("delete", resolved)
        return FileOperationResult(operation="delete", success=True, path=resolved)

    # -- cross-cutting: path policy, confirmation, logging, events -------------

    def _prepare(self, operation: str, path: str | Path) -> Path:
        try:
            resolved = self._guard.check(path)
        except FilesystemAccessError as exc:
            logger.warning(
                "Filesystem operation denied: %s path=%r reason=%s", operation, path, exc
            )
            self._publish(
                "filesystem.denied", {"operation": operation, "path": str(path), "reason": str(exc)}
            )
            raise
        logger.debug("Filesystem operation permitted: %s path=%s", operation, resolved)
        return resolved

    def _require_confirmation(self, operation: str, confirmed: bool) -> None:
        if operation in self._config.require_confirmation and not confirmed:
            logger.warning("Filesystem operation blocked pending confirmation: %s", operation)
            self._publish("filesystem.confirmation_required", {"operation": operation})
            raise ConfirmationRequiredError(
                f"{operation!r} requires confirmation; call again with confirmed=True "
                "after the user has explicitly approved it"
            )

    def _succeed(
        self, operation: str, path: Path, *, destination: Path | None = None, **extra: Any
    ) -> None:
        suffix = f" -> {destination}" if destination is not None else ""
        logger.info("Filesystem operation succeeded: %s path=%s%s", operation, path, suffix)
        payload: dict[str, Any] = {"operation": operation, "path": str(path), **extra}
        if destination is not None:
            payload["destination"] = str(destination)
        self._publish("filesystem.operation_succeeded", payload)

    def _fail(
        self, operation: str, path: Path, exc: OSError, *, destination: Path | None = None
    ) -> NoReturn:
        logger.error("Filesystem operation failed: %s path=%s error=%s", operation, path, exc)
        payload: dict[str, Any] = {"operation": operation, "path": str(path), "error": str(exc)}
        if destination is not None:
            payload["destination"] = str(destination)
        self._publish("filesystem.operation_failed", payload)
        raise FilesystemOperationError(f"{operation} failed for {path}: {exc}") from exc

    def _publish(self, name: str, payload: dict[str, Any]) -> None:
        if self._events is not None:
            self._events.publish(name, payload, source="filesystem_service")
