"""Reusable browser actions: small, named compositions of BrowserPort's
seven primitive capabilities — "implement reusable browser actions"
means these, not just the raw port methods. Each is a plain function
over a BrowserPort so it works against PlaywrightBrowser, NullBrowserPort,
or a test fake identically, and each is independently callable by
ExecutionEngine or anything else without knowing which primitives it
composes.
"""

from __future__ import annotations

from jarvis.core.browser.ports import BrowserPort
from jarvis.core.browser.types import ActionOutcome, PageSummary, SearchResult


def search_and_summarize_top_result(browser: BrowserPort, query: str) -> PageSummary | None:
    """Search, then navigate to and summarize the first result — the
    common "look something up" pattern in one call.
    """
    results = browser.search(query)
    if not results:
        return None
    browser.navigate(results[0].url)
    return browser.summarize_page()


def login(
    browser: BrowserPort,
    url: str,
    *,
    username: str,
    password: str,
    username_field: str = "input[type=email], input[name=username]",
    password_field: str = "input[type=password]",
    submit_selector: str = "button[type=submit]",
) -> ActionOutcome:
    """authenticate() with sensible default selectors for a typical
    login form — override any of them for a site that doesn't match.
    """
    return browser.authenticate(
        url,
        username_field=username_field,
        username=username,
        password_field=password_field,
        password=password,
        submit_selector=submit_selector,
    )


def download_file(browser: BrowserPort, url: str, destination: str) -> str:
    """Thin, named wrapper over download() — exists so callers compose
    actions by name (this module) rather than reaching into BrowserPort
    directly, keeping one place to add retry/logging later.
    """
    return browser.download(url, destination)


def capture_full_page(browser: BrowserPort, url: str, path: str) -> str:
    """Navigate to `url` and screenshot it in one call."""
    browser.navigate(url)
    return browser.screenshot(path)


def search_top_results(browser: BrowserPort, query: str, *, limit: int = 5) -> list[SearchResult]:
    return browser.search(query)[:limit]
