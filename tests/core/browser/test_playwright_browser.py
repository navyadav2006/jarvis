from __future__ import annotations

import sys

import pytest

from jarvis.core.browser.playwright_browser import PlaywrightBrowser
from jarvis.core.config.execution_config import BrowserConfig
from jarvis.core.exceptions import ExecutionBackendUnavailableError


def test_construction_never_touches_network_or_requires_backend() -> None:
    PlaywrightBrowser(BrowserConfig())  # must not raise


def test_missing_backend_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "playwright", None)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    browser = PlaywrightBrowser(BrowserConfig())
    with pytest.raises(ExecutionBackendUnavailableError):
        browser.navigate("https://example.com")


def test_close_without_ever_starting_does_not_raise() -> None:
    PlaywrightBrowser(BrowserConfig()).close()
