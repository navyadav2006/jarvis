"""Plain data types for the Browser Agent.

Independent of orchestrator/'s and core/execution/'s own types — same
"own types per module, bridged by an adapter where needed" rule every
module since core/memory/ has followed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class BrowserEngine(StrEnum):
    """Playwright's three engines — "support future multi-browser
    operation" is this: BrowserConfig.engine picks one per session, and
    nothing above PlaywrightBrowser needs to know which.
    """

    CHROMIUM = "chromium"
    FIREFOX = "firefox"
    WEBKIT = "webkit"


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str = ""


@dataclass(frozen=True)
class PageInfo:
    url: str
    title: str


@dataclass(frozen=True)
class PageSummary:
    """A structural (not LLM-generated) summary of the current page —
    title plus the first few headings/paragraphs of visible text. Real
    summarization is Cowork's job (it already gets page text as
    context); this is what makes that possible without shipping a full
    page dump.
    """

    url: str
    title: str
    headings: list[str] = field(default_factory=list)
    text_excerpt: str = ""


@dataclass(frozen=True)
class ActionOutcome:
    success: bool
    detail: str = ""
