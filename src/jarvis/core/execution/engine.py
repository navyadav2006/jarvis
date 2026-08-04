"""ExecutionEngine: the Desktop Execution Engine (Phase 15) — the one
place Claude Cowork-requested actions (via
orchestrator/execution_adapter.py, wrapping this class as
orchestrator.ports.AutomationPort) actually run. Phase 16 adds an
eighth category, `browser` (core/browser/'s `BrowserPort`) — Cowork
requesting a browser task flows through the exact same
Orchestrator -> AutomationPort -> ExecutionEngine path every other
category already uses, so "Claude Cowork should request browser tasks
through Jarvis" needed no new plumbing here.

Two independent config files combine here, deliberately kept separate:

  - `permissions.yaml` (`PermissionsConfig`, Phase 3, unenforced until
    now) decides *who* may do *what*: `is_allowed(requested_by, scope)`.
    Every action maps to a scope string via
    `core/security/levels.py`'s `PERMISSION_SCOPES` (Phase 19) — shared
    with `SecurityManager` so the two agree on what scope a given
    action needs; see that module's docstring for why this used to be
    a private table here and isn't anymore.
  - `execution.yaml` (`ExecutionConfig`) configures the engine's own
    mechanics — which terminal commands exist at all, timeouts, audit
    log location — orthogonal to who's allowed to use them.

Every call to `execute()` produces exactly one `AuditEntry` (audit.py),
whether the request was denied, succeeded, or raised — "generate an
execution audit trail" means every attempt is recorded, not just
successful ones.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from pathlib import Path

from jarvis.core.browser.ports import BrowserPort
from jarvis.core.config.permissions_config import PermissionsConfig
from jarvis.core.events import EventBus
from jarvis.core.exceptions import ExecutionError, UnknownActionError
from jarvis.core.execution.audit import AuditTrail
from jarvis.core.execution.ports import (
    ApplicationPort,
    ClipboardPort,
    DesktopAutomationPort,
    ScreenshotPort,
    TerminalPort,
    WindowPort,
)
from jarvis.core.execution.types import (
    ActionCategory,
    AuditEntry,
    ExecutionRequest,
    ExecutionResult,
)
from jarvis.core.filesystem.port import FilesystemPort
from jarvis.core.security.levels import PERMISSION_SCOPES

logger = logging.getLogger(__name__)


class ExecutionEngine:
    def __init__(
        self,
        *,
        filesystem: FilesystemPort,
        terminal: TerminalPort,
        desktop: DesktopAutomationPort,
        application: ApplicationPort,
        clipboard: ClipboardPort,
        screenshot: ScreenshotPort,
        window: WindowPort,
        browser: BrowserPort,
        permissions: PermissionsConfig,
        audit_log_path: Path,
        events: EventBus | None = None,
    ) -> None:
        self._filesystem = filesystem
        self._terminal = terminal
        self._desktop = desktop
        self._application = application
        self._clipboard = clipboard
        self._screenshot = screenshot
        self._window = window
        self._browser = browser
        self._permissions = permissions
        self._audit = AuditTrail(audit_log_path)
        self._events = events

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        start = time.monotonic()
        scope = PERMISSION_SCOPES.get((request.category.value, request.action))
        allowed = scope is not None and self._permissions.is_allowed(request.requested_by, scope)

        if not allowed:
            result = ExecutionResult(
                success=False,
                error=f"permission denied for {request.requested_by!r}: "
                f"{request.category.value}.{request.action}",
            )
            self._record(request, result, allowed=False, start=start)
            self._publish("execution.denied", request)
            logger.warning(
                "Execution denied: requester=%r action=%s.%s",
                request.requested_by,
                request.category.value,
                request.action,
            )
            return result

        try:
            output = self._dispatch(request)
            result = ExecutionResult(success=True, output=output)
            self._publish("execution.succeeded", request)
        except ExecutionError as exc:
            result = ExecutionResult(success=False, error=str(exc))
            self._publish("execution.failed", request)
            logger.warning(
                "Execution failed: %s.%s: %s", request.category.value, request.action, exc
            )
        except Exception as exc:
            result = ExecutionResult(success=False, error=f"unexpected error: {exc}")
            self._publish("execution.failed", request)
            logger.exception(
                "Unexpected error executing %s.%s", request.category.value, request.action
            )

        self._record(request, result, allowed=True, start=start)
        return result

    # -- dispatch ------------------------------------------------------------

    def _dispatch(self, request: ExecutionRequest) -> object:
        handler = {
            ActionCategory.FILESYSTEM: self._run_filesystem,
            ActionCategory.TERMINAL: self._run_terminal,
            ActionCategory.DESKTOP: self._run_desktop,
            ActionCategory.APPLICATION: self._run_application,
            ActionCategory.CLIPBOARD: self._run_clipboard,
            ActionCategory.SCREENSHOT: self._run_screenshot,
            ActionCategory.WINDOW: self._run_window,
            ActionCategory.BROWSER: self._run_browser,
        }.get(request.category)
        if handler is None:
            raise UnknownActionError(f"unknown category {request.category!r}")
        return handler(request.action, request.parameters)

    def _run_filesystem(self, action: str, params: dict) -> object:
        confirmed = bool(params.get("confirmed", False))
        if action == "read":
            return self._filesystem.read(params["path"])
        if action == "write":
            return self._filesystem.write(params["path"], params["content"], confirmed=confirmed)
        if action == "copy":
            return self._filesystem.copy(
                params["source"], params["destination"], confirmed=confirmed
            )
        if action == "move":
            return self._filesystem.move(
                params["source"], params["destination"], confirmed=confirmed
            )
        if action == "rename":
            return self._filesystem.rename(params["path"], params["new_name"], confirmed=confirmed)
        if action == "delete":
            return self._filesystem.delete(params["path"], confirmed=confirmed)
        if action == "search":
            return self._filesystem.search(
                params["directory"], params["pattern"], recursive=params.get("recursive", True)
            )
        raise UnknownActionError(f"unknown filesystem action {action!r}")

    def _run_terminal(self, action: str, params: dict) -> object:
        if action != "run":
            raise UnknownActionError(f"unknown terminal action {action!r}")
        exit_code, stdout, stderr = self._terminal.run(
            params["command"], params.get("args", []), timeout=params.get("timeout", 30.0)
        )
        return {"exit_code": exit_code, "stdout": stdout, "stderr": stderr}

    def _run_desktop(self, action: str, params: dict) -> object:
        if action == "click":
            self._desktop.click(params["x"], params["y"])
            return None
        if action == "type_text":
            self._desktop.type_text(params["text"])
            return None
        if action == "key_press":
            self._desktop.key_press(params["key"])
            return None
        raise UnknownActionError(f"unknown desktop action {action!r}")

    def _run_application(self, action: str, params: dict) -> object:
        if action == "launch":
            return self._application.launch(params["path"], params.get("args", []))
        if action == "close":
            return self._application.close(params["process_name"])
        raise UnknownActionError(f"unknown application action {action!r}")

    def _run_clipboard(self, action: str, params: dict) -> object:
        if action == "get":
            return self._clipboard.get()
        if action == "set":
            self._clipboard.set(params["text"])
            return None
        raise UnknownActionError(f"unknown clipboard action {action!r}")

    def _run_screenshot(self, action: str, params: dict) -> object:
        if action != "capture":
            raise UnknownActionError(f"unknown screenshot action {action!r}")
        return self._screenshot.capture(params["path"])

    def _run_window(self, action: str, params: dict) -> object:
        if action == "list":
            return self._window.list_windows()
        if action == "focus":
            return self._window.focus(params["title"])
        if action == "minimize":
            return self._window.minimize(params["title"])
        if action == "maximize":
            return self._window.maximize(params["title"])
        raise UnknownActionError(f"unknown window action {action!r}")

    def _run_browser(self, action: str, params: dict) -> object:
        if action == "search":
            return self._browser.search(params["query"])
        if action == "navigate":
            return self._browser.navigate(params["url"])
        if action == "fill_form":
            return self._browser.fill_form(
                params["fields"], submit=params.get("submit", False)
            )
        if action == "authenticate":
            return self._browser.authenticate(
                params["url"],
                username_field=params["username_field"],
                username=params["username"],
                password_field=params["password_field"],
                password=params["password"],
                submit_selector=params["submit_selector"],
            )
        if action == "download":
            return self._browser.download(params["url"], params["destination"])
        if action == "screenshot":
            return self._browser.screenshot(params["path"])
        if action == "summarize_page":
            return self._browser.summarize_page()
        raise UnknownActionError(f"unknown browser action {action!r}")

    # -- internals -----------------------------------------------------------

    def _record(
        self, request: ExecutionRequest, result: ExecutionResult, *, allowed: bool, start: float
    ) -> None:
        entry = AuditEntry(
            timestamp=datetime.now(UTC),
            category=request.category.value,
            action=request.action,
            requested_by=request.requested_by,
            parameters=request.parameters,
            allowed=allowed,
            success=result.success,
            output=None if result.output is None else str(result.output)[:2000],
            error=result.error,
            duration_seconds=time.monotonic() - start,
        )
        self._audit.record(entry)

    def _publish(self, name: str, request: ExecutionRequest) -> None:
        if self._events is not None:
            self._events.publish(
                name,
                {
                    "category": request.category.value,
                    "action": request.action,
                    "requested_by": request.requested_by,
                },
                source="execution_engine",
            )
