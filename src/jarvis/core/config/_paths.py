"""Shared path constants for the config package.

Split into its own module (rather than living in one of the domain
files) so every domain module and manager.py can import PROJECT_ROOT /
DEFAULT_CONFIG_DIR without importing each other.

BUG FIX (voice-wiring/Cowork-correction follow-up): `Path(__file__)` is
only the real source location when running from source. Inside a
PyInstaller onefile build, every bundled module's `__file__` resolves
into the temporary extraction directory (`sys._MEIPASS`, a fresh
`%TEMP%\\_MEIxxxxx` folder each run) — so `.parents[4]` from there
landed somewhere under Temp, not the actual project root next to
`jarvis.exe`. `DEFAULT_CONFIG_DIR` then pointed at a `config/` that
never existed, and `ConfigManager`'s fail-safe "missing directory ->
use every domain's pydantic defaults" behavior silently activated —
every capability read as disabled with no error, indistinguishable
from a correctly-loaded default-off config. This was invisible for as
long as every domain's default happened to be off; it stopped being
invisible the moment `config/*.yaml` started asking for anything
non-default (cowork/execution/memory/vault/voice `enabled: true`).
`scripts/run_jarvis_exe.py` already `os.chdir()`s to the exe's own
directory before importing `jarvis.main` for exactly this reason — this
fix makes the same directory the source of truth here too, so any
future entry point gets it right without relying on chdir happening
first.
"""

from __future__ import annotations

import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    # PyInstaller-built executable: __file__ resolves inside the
    # extraction temp dir, not next to jarvis.exe. Use the exe's own
    # directory instead — see scripts/run_jarvis_exe.py, which places
    # jarvis.exe at the repo root.
    PROJECT_ROOT = Path(sys.executable).resolve().parent
else:
    PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CONFIG_DIR = PROJECT_ROOT / "config"
