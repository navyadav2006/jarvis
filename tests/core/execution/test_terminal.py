from __future__ import annotations

import sys

import pytest

from jarvis.core.config.execution_config import TerminalConfig
from jarvis.core.exceptions import ExecutionBackendUnavailableError
from jarvis.core.execution.terminal import SubprocessTerminal


def test_disallowed_command_is_rejected() -> None:
    terminal = SubprocessTerminal(TerminalConfig(allowed_commands=["git"]))
    with pytest.raises(ExecutionBackendUnavailableError):
        terminal.run("rm", ["-rf", "/"], timeout=5.0)


def test_allowed_command_runs_and_captures_output() -> None:
    terminal = SubprocessTerminal(TerminalConfig(allowed_commands=[sys.executable]))
    exit_code, stdout, stderr = terminal.run(
        sys.executable, ["-c", "print('hello')"], timeout=10.0
    )
    assert exit_code == 0
    assert "hello" in stdout


def test_nonzero_exit_code_is_returned_not_raised() -> None:
    terminal = SubprocessTerminal(TerminalConfig(allowed_commands=[sys.executable]))
    exit_code, stdout, stderr = terminal.run(
        sys.executable, ["-c", "import sys; sys.exit(3)"], timeout=10.0
    )
    assert exit_code == 3


def test_timeout_raises_backend_unavailable() -> None:
    terminal = SubprocessTerminal(
        TerminalConfig(allowed_commands=[sys.executable], timeout_seconds=0.1)
    )
    with pytest.raises(ExecutionBackendUnavailableError):
        terminal.run(sys.executable, ["-c", "import time; time.sleep(5)"], timeout=10.0)


def test_stderr_is_captured() -> None:
    terminal = SubprocessTerminal(TerminalConfig(allowed_commands=[sys.executable]))
    _, _, stderr = terminal.run(
        sys.executable,
        ["-c", "import sys; print('oops', file=sys.stderr)"],
        timeout=10.0,
    )
    assert "oops" in stderr
