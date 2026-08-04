"""PlaywrightBrowser: a real BrowserPort implementation backed by
Playwright's synchronous API, lazily imported — install the 'browser'
extra (`pip install -e '.[browser]'`) AND run `playwright install
<engine>` (a separate binary download pip alone cannot do) before using
it. Constructing this class never requires Playwright to be installed;
only a real call does.

One `PlaywrightBrowser` instance holds one browser + one page, launched
lazily on first use and reused across calls — the same "stay resident,
don't restart per call" reasoning whisper.cpp/Piper's real backends
used (Phase 6/7). `BrowserConfig.engine` picks chromium/firefox/webkit
at launch time; nothing else in this class or in ExecutionEngine cares
which, which is what "support future multi-browser operation" means
here — running two `PlaywrightBrowser`s with different `engine`s (or
concurrent sessions generally) is a caller-level composition this class
doesn't need to change to support.

NOTE: `search()`'s default target (DuckDuckGo's HTML endpoint) is
scraped via CSS selectors, not an API — like every other "real but
fragile, HTML/API shape unverified against a live install" integration
in this project (Cowork's HTTP contract, Piper/openWakeWord's Python
APIs), this will break if that page's markup changes. `search_url_template`
and the result selectors are the two places to update if it does.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote

from jarvis.core.browser.types import ActionOutcome, PageInfo, PageSummary, SearchResult
from jarvis.core.config.execution_config import BrowserConfig
from jarvis.core.exceptions import ExecutionBackendUnavailableError

_RESULT_LINK_SELECTOR = "a.result__a"
_RESULT_SNIPPET_SELECTOR = ".result__snippet"


class PlaywrightBrowser:
    """Implements core.browser.ports.BrowserPort."""

    def __init__(self, config: BrowserConfig) -> None:
        self._config = config
        self._playwright: Any = None
        self._browser: Any = None
        self._page: Any = None

    def search(self, query: str) -> list[SearchResult]:
        page = self._ensure_page()
        url = self._config.search_url_template.format(query=quote(query))
        page.goto(url, timeout=self._config.timeout_seconds * 1000)
        links = page.query_selector_all(_RESULT_LINK_SELECTOR)
        snippets = page.query_selector_all(_RESULT_SNIPPET_SELECTOR)
        results = []
        for i, link in enumerate(links):
            snippet = snippets[i].inner_text() if i < len(snippets) else ""
            results.append(
                SearchResult(
                    title=link.inner_text(),
                    url=link.get_attribute("href") or "",
                    snippet=snippet,
                )
            )
        return results

    def navigate(self, url: str) -> PageInfo:
        page = self._ensure_page()
        page.goto(url, timeout=self._config.timeout_seconds * 1000)
        return PageInfo(url=page.url, title=page.title())

    def fill_form(self, fields: dict[str, str], *, submit: bool = False) -> ActionOutcome:
        page = self._ensure_page()
        for selector, value in fields.items():
            page.fill(selector, value)
        if submit and fields:
            page.keyboard.press("Enter")
        return ActionOutcome(success=True, detail=f"filled {len(fields)} field(s)")

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
        self.navigate(url)
        self.fill_form({username_field: username, password_field: password})
        page = self._ensure_page()
        page.click(submit_selector)
        return ActionOutcome(success=True, detail=f"authenticated at {url}")

    def download(self, url: str, destination: str) -> str:
        page = self._ensure_page()
        with page.expect_download(timeout=self._config.timeout_seconds * 1000) as download_info:
            page.goto(url)
        download = download_info.value
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        download.save_as(destination)
        return destination

    def screenshot(self, path: str) -> str:
        page = self._ensure_page()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=path)
        return path

    def summarize_page(self) -> PageSummary:
        page = self._ensure_page()
        headings = page.eval_on_selector_all(
            "h1, h2, h3", "elements => elements.map(e => e.innerText)"
        )
        body_text = page.inner_text("body")
        return PageSummary(
            url=page.url, title=page.title(), headings=headings, text_excerpt=body_text[:500]
        )

    def close(self) -> None:
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None
        self._page = None

    # -- internals ---------------------------------------------------------

    def _ensure_page(self) -> Any:
        if self._page is not None:
            return self._page

        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise ExecutionBackendUnavailableError(
                "playwright is not installed; install the 'browser' extra "
                "(pip install -e '.[browser]') and run 'playwright install "
                f"{self._config.engine}' to use the Browser Agent"
            ) from exc

        self._playwright = sync_playwright().start()
        launcher = getattr(self._playwright, self._config.engine)
        self._browser = launcher.launch(headless=self._config.headless)
        context = self._browser.new_context(accept_downloads=True)
        self._page = context.new_page()
        return self._page
