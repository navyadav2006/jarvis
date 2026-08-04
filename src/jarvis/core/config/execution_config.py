"""execution.yaml — the Desktop Execution Engine's settings (Phase 15):
which terminal commands are permitted, timeouts, and where the
execution audit trail is written.

Permission *scopes* themselves (which requester may use which action
category) are governed by the existing `permissions.yaml`
(`PermissionsConfig`, Phase 3) — this file only configures the engine's
own mechanics, not who's allowed to do what. See
core/execution/engine.py's module docstring for how the two combine.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EXECUTION_FILENAME = "execution.yaml"


class TerminalConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    # Allowlist of executable names (not full paths, not arbitrary
    # shell strings) the terminal category may run. Empty by default —
    # deny-by-default, matching filesystem.yaml's allowlist philosophy.
    allowed_commands: list[str] = Field(default_factory=list)
    timeout_seconds: float = Field(30.0, gt=0.0)


class BrowserConfig(BaseModel):
    """The Browser Agent's settings (Phase 16). Nested inside
    ExecutionConfig rather than a 10th top-level YAML file, the same
    way TerminalConfig is — one more execution category, not a new
    config domain.
    """

    model_config = ConfigDict(frozen=True)

    enabled: bool = False
    # Which of Playwright's three engines to launch — this is the
    # "support future multi-browser operation" knob: nothing above
    # PlaywrightBrowser needs to know or care which one is active.
    engine: Literal["chromium", "firefox", "webkit"] = "chromium"
    headless: bool = True
    download_dir: Path = Path("data/browser/downloads")
    timeout_seconds: float = Field(30.0, gt=0.0)
    # The search results page navigate()/search() loads — configurable
    # since scraping any one search engine's HTML is inherently fragile
    # (see playwright_browser.py's module docstring).
    search_url_template: str = "https://html.duckduckgo.com/html/?q={query}"


class ExecutionConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    enabled: bool = False
    audit_log_path: Path = Path("logs/execution_audit.jsonl")
    terminal: TerminalConfig = Field(default_factory=TerminalConfig)
    browser: BrowserConfig = Field(default_factory=BrowserConfig)

    # The `plugin` identity ExecutionEngine checks against
    # permissions.yaml when a request doesn't specify its own
    # `requested_by` — Cowork-originated actions use this.
    default_requester: str = "cowork"
