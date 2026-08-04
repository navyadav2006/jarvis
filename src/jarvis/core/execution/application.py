"""ProcessApplicationManager: a real ApplicationPort implementation
over `subprocess`/`os` only — no new dependency needed for launch or
close, unlike desktop/clipboard/screenshot/window below.

`close()` uses `taskkill` on Windows and `SIGTERM` via `os.kill` on
POSIX — both stdlib-reachable (subprocess/os), matching the
"no new dependency where the standard library already suffices"
choice `SqliteMemoryManager`/`VaultService` made in earlier phases.
"""

from __future__ import annotations

import logging
import subprocess
import sys

from jarvis.core.exceptions import ExecutionBackendUnavailableError

logger = logging.getLogger(__name__)


class ProcessApplicationManager:
    """Implements core.execution.ports.ApplicationPort."""

    def launch(self, path: str, args: list[str]) -> int:
        logger.info("Launching application: %r %r", path, args)
        try:
            process = subprocess.Popen([path, *args])  # noqa: S603 — argv list, shell=False
        except OSError as exc:
            raise ExecutionBackendUnavailableError(f"could not launch {path!r}: {exc}") from exc
        return process.pid

    def close(self, process_name: str) -> bool:
        logger.info("Closing application: %r", process_name)
        if sys.platform == "win32":
            completed = subprocess.run(  # noqa: S603, S607
                ["taskkill", "/IM", process_name, "/F"],
                capture_output=True,
                text=True,
                check=False,
            )
            return completed.returncode == 0
        completed = subprocess.run(  # noqa: S603, S607
            ["pkill", "-f", process_name], capture_output=True, text=True, check=False
        )
        return completed.returncode == 0
