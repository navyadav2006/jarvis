"""BrowserPort: the abstract interface for the Browser Agent (Phase 16)
— one active page per session, driven through seven capabilities.
`PlaywrightBrowser` (playwright_browser.py) is the one real
implementation; `NullBrowserPort` is the safe default, following every
other module's Null Object convention.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from jarvis.core.browser.types import ActionOutcome, PageInfo, PageSummary, SearchResult
from jarvis.core.exceptions import ExecutionBackendUnavailableError

_NO_BACKEND = "no browser backend configured"


@runtime_checkable
class BrowserPort(Protocol):
    def search(self, query: str) -> list[SearchResult]: ...

    def navigate(self, url: str) -> PageInfo: ...

    def fill_form(self, fields: dict[str, str], *, submit: bool = False) -> ActionOutcome: ...

    def authenticate(
        self,
        url: str,
        *,
        username_field: str,
        username: str,
        password_field: str,
        password: str,
        submit_selector: str,
    ) -> ActionOutcome: ...

    def download(self, url: str, destination: str) -> str:
        """Trigger a download from `url`; returns the path it was saved to."""
        ...

    def screenshot(self, path: str) -> str: ...

    def summarize_page(self) -> PageSummary: ...

    def close(self) -> None: ...


class NullBrowserPort:
    """No browser backend configured. Every capability raises
    ExecutionBackendUnavailableError rather than silently no-op'ing —
    a caller asking Jarvis to navigate somewhere deserves to know
    nothing happened, the same convention core/execution/ports.py's
    Null handlers use.
    """

    def search(self, query: str) -> list[SearchResult]:
        raise ExecutionBackendUnavailableError(_NO_BACKEND)

    def navigate(self, url: str) -> PageInfo:
        raise ExecutionBackendUnavailableError(_NO_BACKEND)

    def fill_form(self, fields: dict[str, str], *, submit: bool = False) -> ActionOutcome:
        raise ExecutionBackendUnavailableError(_NO_BACKEND)

    def authenticate(
        self,
        url: str,
        *,
        username_field: str,
        username: str,
        password_field: str,
        password: str,
        submit_selector: str,
    ) -> ActionOutcome:
        raise ExecutionBackendUnavailableError(_NO_BACKEND)

    def download(self, url: str, destination: str) -> str:
        raise ExecutionBackendUnavailableError(_NO_BACKEND)

    def screenshot(self, path: str) -> str:
        raise ExecutionBackendUnavailableError(_NO_BACKEND)

    def summarize_page(self) -> PageSummary:
        raise ExecutionBackendUnavailableError(_NO_BACKEND)

    def close(self) -> None:
        pass  # nothing to close
