"""PyInstaller entry point for the packaged Jarvis executable.

Ensures the process working directory is the Jarvis project root (so
config/, data/, plugins/, vault/, prompts/ resolve the same way they do
when running `python -m jarvis.main` from the repo) before delegating to
the real startup sequence in jarvis.main.
"""

from __future__ import annotations

import os
import sys


def _project_root() -> str:
    if getattr(sys, "frozen", False):
        # Running as a PyInstaller-built exe: the project root is the
        # directory the exe itself lives in (see build_exe.py, which
        # places jarvis.exe at the repo root).
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


if __name__ == "__main__":
    os.chdir(_project_root())
    from jarvis.main import main

    main()
