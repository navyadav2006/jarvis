from __future__ import annotations

import sys

import pytest

from jarvis.core.exceptions import ExecutionBackendUnavailableError
from jarvis.core.execution.application import ProcessApplicationManager


def test_launch_returns_a_pid() -> None:
    manager = ProcessApplicationManager()
    pid = manager.launch(sys.executable, ["-c", "import time; time.sleep(0.5)"])
    assert pid > 0


def test_launch_nonexistent_executable_raises() -> None:
    manager = ProcessApplicationManager()
    with pytest.raises(ExecutionBackendUnavailableError):
        manager.launch("this_executable_does_not_exist_xyz", [])


def test_close_with_no_matching_process_returns_false() -> None:
    # Deliberately does NOT test closing a real process: `close()` kills
    # by image name (taskkill /IM, or pkill -f), which would match every
    # process sharing that name — including, for "python", this test
    # runner itself. A nonexistent name is the only safe case to assert.
    manager = ProcessApplicationManager()
    assert manager.close("definitely_not_a_running_process_xyz.exe") is False
