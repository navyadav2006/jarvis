"""SubprocessTerminal: a real TerminalPort implementation over the
standard library's `subprocess` — no new dependency.

Safety is an allowlist of bare executable names (`TerminalConfig.
allowed_commands`), checked before anything runs, and
`shell=False`/argv-list execution throughout — `command` and `args` are
passed straight to `subprocess.run` as a list, never through a shell,
so there is no shell-metacharacter injection surface (`;`, `&&`, `|`,
etc. are just literal argument characters, not interpreted).
"""

from __future__ import annotations

import logging
import subprocess

from jarvis.core.config.execution_config import TerminalConfig
from jarvis.core.exceptions import ExecutionBackendUnavailableError

logger = logging.getLogger(__name__)


class SubprocessTerminal:
    """Implements core.execution.ports.TerminalPort."""

    def __init__(self, config: TerminalConfig) -> None:
        self._config = config

    def run(self, command: str, args: list[str], *, timeout: float) -> tuple[int, str, str]:
        if command not in self._config.allowed_commands:
            raise ExecutionBackendUnavailableError(
                f"command {command!r} is not on the terminal allowlist "
                "(update execution.yaml's terminal.allowed_commands)"
            )
        effective_timeout = min(timeout, self._config.timeout_seconds)
        logger.info("Running terminal command: %r %r", command, args)
        try:
            completed = subprocess.run(  # noqa: S603 — argv list, shell=False, allowlisted
                [command, *args],
                capture_output=True,
                text=True,
                timeout=effective_timeout,
                shell=False,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ExecutionBackendUnavailableError(
                f"command {command!r} did not complete within {effective_timeout}s"
            ) from exc
        except OSError as exc:
            raise ExecutionBackendUnavailableError(
                f"command {command!r} failed to start: {exc}"
            ) from exc
        return completed.returncode, completed.stdout, completed.stderr
