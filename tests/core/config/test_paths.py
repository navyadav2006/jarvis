"""Regression test for a real bug (voice-wiring/Cowork-correction
follow-up): PROJECT_ROOT was computed from `Path(__file__)`, which
inside a PyInstaller onefile build resolves into the temp extraction
directory rather than next to jarvis.exe — silently pointing
DEFAULT_CONFIG_DIR/PathsSettings.resolved() at a `config/` that never
existed, so every domain quietly fell back to its pydantic defaults
with no error. See core/config/_paths.py's module docstring.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import jarvis.core.config._paths as paths_module


def test_project_root_uses_executable_directory_when_frozen(monkeypatch) -> None:
    fake_exe = Path("C:/fake/install/dir/jarvis.exe")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe))
    try:
        reloaded = importlib.reload(paths_module)
        assert reloaded.PROJECT_ROOT == fake_exe.resolve().parent
        assert reloaded.DEFAULT_CONFIG_DIR == fake_exe.resolve().parent / "config"
    finally:
        monkeypatch.delattr(sys, "frozen", raising=False)
        importlib.reload(paths_module)  # restore the real, source-based PROJECT_ROOT


def test_project_root_uses_source_file_location_when_not_frozen() -> None:
    assert not getattr(sys, "frozen", False)
    # __file__ is src/jarvis/core/config/_paths.py — parents[4] from there is the repo root.
    assert (paths_module.PROJECT_ROOT / "src" / "jarvis" / "core" / "config").is_dir()
    assert paths_module.DEFAULT_CONFIG_DIR == paths_module.PROJECT_ROOT / "config"
