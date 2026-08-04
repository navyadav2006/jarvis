"""PyperclipClipboard: a real ClipboardPort implementation backed by
`pyperclip`, lazily imported — install the 'desktop' extra to use it.
"""

from __future__ import annotations

from typing import Any

from jarvis.core.exceptions import ExecutionBackendUnavailableError


class PyperclipClipboard:
    """Implements core.execution.ports.ClipboardPort."""

    def get(self) -> str:
        return self._ensure_backend().paste()

    def set(self, text: str) -> None:
        self._ensure_backend().copy(text)

    def _ensure_backend(self) -> Any:
        try:
            import pyperclip
        except ImportError as exc:
            raise ExecutionBackendUnavailableError(
                "pyperclip is not installed; install the 'desktop' extra "
                "(pip install -e '.[desktop]') to use the clipboard"
            ) from exc
        return pyperclip
