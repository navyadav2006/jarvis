"""PyGetWindowManager: a real WindowPort implementation backed by
`pygetwindow`, lazily imported — install the 'desktop' extra to use it.
"""

from __future__ import annotations

from typing import Any

from jarvis.core.exceptions import ExecutionBackendUnavailableError


class PyGetWindowManager:
    """Implements core.execution.ports.WindowPort."""

    def list_windows(self) -> list[str]:
        gw = self._ensure_backend()
        return [w.title for w in gw.getAllWindows() if w.title]

    def focus(self, title: str) -> bool:
        return self._apply(title, lambda w: w.activate())

    def minimize(self, title: str) -> bool:
        return self._apply(title, lambda w: w.minimize())

    def maximize(self, title: str) -> bool:
        return self._apply(title, lambda w: w.maximize())

    def _apply(self, title: str, action) -> bool:
        gw = self._ensure_backend()
        matches = gw.getWindowsWithTitle(title)
        if not matches:
            return False
        action(matches[0])
        return True

    def _ensure_backend(self) -> Any:
        try:
            import pygetwindow as gw
        except ImportError as exc:
            raise ExecutionBackendUnavailableError(
                "pygetwindow is not installed; install the 'desktop' extra "
                "(pip install -e '.[desktop]') to manage windows"
            ) from exc
        return gw
