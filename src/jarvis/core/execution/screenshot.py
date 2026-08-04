"""PillowScreenshotter: a real ScreenshotPort implementation backed by
Pillow's `ImageGrab`, lazily imported — install the 'desktop' extra to
use it.
"""

from __future__ import annotations

from jarvis.core.exceptions import ExecutionBackendUnavailableError


class PillowScreenshotter:
    """Implements core.execution.ports.ScreenshotPort."""

    def capture(self, path: str) -> str:
        try:
            from PIL import ImageGrab
        except ImportError as exc:
            raise ExecutionBackendUnavailableError(
                "Pillow is not installed; install the 'desktop' extra "
                "(pip install -e '.[desktop]') to take screenshots"
            ) from exc
        image = ImageGrab.grab()
        image.save(path)
        return path
