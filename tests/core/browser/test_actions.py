from __future__ import annotations

from jarvis.core.browser import actions
from jarvis.core.browser.types import ActionOutcome, PageInfo, PageSummary, SearchResult


class FakeBrowser:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.search_results: list[SearchResult] = []

    def search(self, query: str) -> list[SearchResult]:
        self.calls.append(("search", query))
        return self.search_results

    def navigate(self, url: str) -> PageInfo:
        self.calls.append(("navigate", url))
        return PageInfo(url=url, title="Title")

    def fill_form(self, fields, *, submit=False):
        self.calls.append(("fill_form", fields, submit))
        return ActionOutcome(success=True)

    def authenticate(self, url, **kwargs):
        self.calls.append(("authenticate", url, kwargs))
        return ActionOutcome(success=True, detail=f"authenticated at {url}")

    def download(self, url: str, destination: str) -> str:
        self.calls.append(("download", url, destination))
        return destination

    def screenshot(self, path: str) -> str:
        self.calls.append(("screenshot", path))
        return path

    def summarize_page(self) -> PageSummary:
        self.calls.append(("summarize_page",))
        return PageSummary(url="https://example.com", title="Title")

    def close(self) -> None:
        self.calls.append(("close",))


def test_search_and_summarize_top_result_navigates_then_summarizes() -> None:
    browser = FakeBrowser()
    browser.search_results = [SearchResult(title="A", url="https://a.example.com")]

    summary = actions.search_and_summarize_top_result(browser, "query")

    assert summary is not None
    assert ("navigate", "https://a.example.com") in browser.calls
    assert ("summarize_page",) in browser.calls


def test_search_and_summarize_top_result_returns_none_when_no_results() -> None:
    browser = FakeBrowser()
    assert actions.search_and_summarize_top_result(browser, "query") is None


def test_login_calls_authenticate_with_default_selectors() -> None:
    browser = FakeBrowser()
    outcome = actions.login(
        browser, "https://example.com/login", username="me", password="secret"
    )
    assert outcome.success is True
    call = browser.calls[0]
    assert call[0] == "authenticate"
    assert call[2]["username"] == "me"
    assert call[2]["password"] == "secret"


def test_login_allows_custom_selectors() -> None:
    browser = FakeBrowser()
    actions.login(
        browser,
        "https://example.com/login",
        username="me",
        password="secret",
        username_field="#user",
        password_field="#pass",
        submit_selector="#go",
    )
    call = browser.calls[0]
    assert call[2]["username_field"] == "#user"
    assert call[2]["submit_selector"] == "#go"


def test_download_file_delegates_to_browser() -> None:
    browser = FakeBrowser()
    result = actions.download_file(browser, "https://example.com/f.zip", "out/f.zip")
    assert result == "out/f.zip"
    assert ("download", "https://example.com/f.zip", "out/f.zip") in browser.calls


def test_capture_full_page_navigates_then_screenshots() -> None:
    browser = FakeBrowser()
    result = actions.capture_full_page(browser, "https://example.com", "out.png")
    assert result == "out.png"
    assert browser.calls[0] == ("navigate", "https://example.com")
    assert browser.calls[1] == ("screenshot", "out.png")


def test_search_top_results_respects_limit() -> None:
    browser = FakeBrowser()
    browser.search_results = [SearchResult(title=f"R{i}", url=f"u{i}") for i in range(10)]
    results = actions.search_top_results(browser, "query", limit=3)
    assert len(results) == 3
