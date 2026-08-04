"""PyAutoGuiDesktopAutomation: a real DesktopAutomationPort implementation
backed by `pyautogui`, lazily imported — install the 'desktop' extra
(`pip install -e '.[desktop]'`) to use it. Constructing this class never
requires pyautogui to be installed; only a real click()/type_text()/
key_press() call does.
"""

from __future__ import annotations

import logging
from typing import Any

from jarvis.core.exceptions import ExecutionBackendUnavailableError

logger = logging.getLogger(__name__)


class PyAutoGuiDesktopAutomation:
    """Implements core.execution.ports.DesktopAutomationPort."""

    def click(self, x: int, y: int) -> None:
        pyautogui = self._ensure_backend()
        pyautogui.click(x, y)

    def type_text(self, text: str) -> None:
        pyautogui = self._ensure_backend()
        pyautogui.typewrite(text)

    def key_press(self, key: str) -> None:
        pyautogui = self._ensure_backend()
        pyautogui.press(key)

    def _ensure_backend(self) -> Any:
        try:
            import pyautogui
        except ImportError as exc:
            raise ExecutionBackendUnavailableError(
                "pyautogui is not installed; install the 'desktop' extra "
                "(pip install -e '.[desktop]') to use desktop automation"
            ) from exc
        return pyautogui
