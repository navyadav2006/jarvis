from __future__ import annotations

import pytest

from jarvis.core.browser.ports import BrowserPort, NullBrowserPort
from jarvis.core.exceptions import ExecutionBackendUnavailableError


def test_null_browser_satisfies_protocol() -> None:
    assert isinstance(NullBrowserPort(), BrowserPort)


def test_null_browser_raises_on_every_capability() -> None:
    port = NullBrowserPort()
    with pytest.raises(ExecutionBackendUnavailableError):
        port.search("query")
    with pytest.raises(ExecutionBackendUnavailableError):
        port.navigate("https://example.com")
    with pytest.raises(ExecutionBackendUnavailableError):
        port.fill_form({})
    with pytest.raises(ExecutionBackendUnavailableError):
        port.authenticate(
            "https://example.com",
            username_field="u",
            username="a",
            password_field="p",
            password="b",
            submit_selector="button",
        )
    with pytest.raises(ExecutionBackendUnavailableError):
        port.download("https://example.com/f", "f.bin")
    with pytest.raises(ExecutionBackendUnavailableError):
        port.screenshot("out.png")
    with pytest.raises(ExecutionBackendUnavailableError):
        port.summarize_page()


def test_null_browser_close_is_a_safe_noop() -> None:
    NullBrowserPort().close()  # must not raise
