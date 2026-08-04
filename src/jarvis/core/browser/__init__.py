"""The Browser Agent (Phase 16): search, navigate, fill forms,
authenticate, download files, capture screenshots, and summarize
pages — via Playwright, lazily imported (the 'browser' extra).

`BrowserPort` is a category handler exactly like core/execution/'s
Terminal/Application/Clipboard/etc. ports — `ExecutionEngine` gained a
`browser` category and dispatches to it, so "Claude Cowork should
request browser tasks through Jarvis" needed no new integration point:
Cowork already requests `AutomationAction`s through
`Orchestrator._try_cowork()` (Phase 9), which already flows into
`ExecutionEngine` (Phase 15). `actions.py` composes the seven
primitives into a few reusable, named higher-level actions.
"""

from __future__ import annotations

from jarvis.core.browser.actions import (
    capture_full_page,
    download_file,
    login,
    search_and_summarize_top_result,
    search_top_results,
)
from jarvis.core.browser.playwright_browser import PlaywrightBrowser
from jarvis.core.browser.ports import BrowserPort, NullBrowserPort
from jarvis.core.browser.types import (
    ActionOutcome,
    BrowserEngine,
    PageInfo,
    PageSummary,
    SearchResult,
)

__all__ = [
    "ActionOutcome",
    "BrowserEngine",
    "BrowserPort",
    "NullBrowserPort",
    "PageInfo",
    "PageSummary",
    "PlaywrightBrowser",
    "SearchResult",
    "capture_full_page",
    "download_file",
    "login",
    "search_and_summarize_top_result",
    "search_top_results",
]
