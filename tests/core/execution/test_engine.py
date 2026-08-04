from __future__ import annotations

import json

from jarvis.core.config.permissions_config import PermissionsConfig
from jarvis.core.events import EventBus
from jarvis.core.execution.engine import ExecutionEngine
from jarvis.core.execution.types import ActionCategory, ExecutionRequest


def _req(category: str, action: str, **params) -> ExecutionRequest:
    return ExecutionRequest(
        category=ActionCategory(category), action=action, parameters=params, requested_by="cowork"
    )


def test_allowed_filesystem_write_succeeds(engine, handlers) -> None:
    result = engine.execute(_req("filesystem", "write", path="a.md", content="hi"))
    assert result.success is True
    assert handlers["filesystem"].files["a.md"] == "hi"


def test_denied_action_returns_failure_not_exception(handlers, tmp_path) -> None:
    deny_all = PermissionsConfig(default_policy="deny", rules=[])
    engine = ExecutionEngine(
        filesystem=handlers["filesystem"],
        terminal=handlers["terminal"],
        desktop=handlers["desktop"],
        application=handlers["application"],
        clipboard=handlers["clipboard"],
        screenshot=handlers["screenshot"],
        window=handlers["window"],
        browser=handlers["browser"],
        permissions=deny_all,
        audit_log_path=tmp_path / "audit.jsonl",
    )
    result = engine.execute(_req("filesystem", "write", path="a.md", content="hi"))
    assert result.success is False
    assert "permission denied" in result.error
    assert handlers["filesystem"].files == {}  # never actually ran


def test_unknown_scope_is_denied_even_with_default_allow(handlers, tmp_path) -> None:
    allow_all = PermissionsConfig(default_policy="allow", rules=[])
    engine = ExecutionEngine(
        filesystem=handlers["filesystem"],
        terminal=handlers["terminal"],
        desktop=handlers["desktop"],
        application=handlers["application"],
        clipboard=handlers["clipboard"],
        screenshot=handlers["screenshot"],
        window=handlers["window"],
        browser=handlers["browser"],
        permissions=allow_all,
        audit_log_path=tmp_path / "audit.jsonl",
    )
    # "bogus" isn't a real filesystem action, so it has no _SCOPES entry
    # at all — must be denied regardless of default_policy=allow.
    result = engine.execute(_req("filesystem", "bogus"))
    assert result.success is False


def test_terminal_run_dispatches_to_handler(engine, handlers) -> None:
    result = engine.execute(_req("terminal", "run", command="git", args=["status"]))
    assert result.success is True
    assert handlers["terminal"].calls == [("git", ["status"])]
    assert result.output["exit_code"] == 0


def test_desktop_click_dispatches_to_handler(engine, handlers) -> None:
    engine.execute(_req("desktop", "click", x=10, y=20))
    assert handlers["desktop"].calls == [("click", 10, 20)]


def test_application_launch_and_close(engine, handlers) -> None:
    launch_result = engine.execute(_req("application", "launch", path="notepad.exe", args=[]))
    assert launch_result.output == 4242
    close_result = engine.execute(_req("application", "close", process_name="notepad.exe"))
    assert close_result.output is True


def test_clipboard_set_then_get(engine, handlers) -> None:
    engine.execute(_req("clipboard", "set", text="hello"))
    result = engine.execute(_req("clipboard", "get"))
    assert result.output == "hello"


def test_screenshot_capture(engine) -> None:
    result = engine.execute(_req("screenshot", "capture", path="out.png"))
    assert result.output == "out.png"


def test_window_list_and_focus(engine) -> None:
    listed = engine.execute(_req("window", "list"))
    assert listed.output == ["Window A", "Window B"]
    focused = engine.execute(_req("window", "focus", title="Window A"))
    assert focused.output is True


def test_browser_search_dispatches_to_handler(engine, handlers) -> None:
    engine.execute(_req("browser", "search", query="jarvis ai assistant"))
    assert handlers["browser"].calls == [("search", "jarvis ai assistant")]


def test_browser_navigate_and_screenshot(engine, handlers) -> None:
    engine.execute(_req("browser", "navigate", url="https://example.com"))
    result = engine.execute(_req("browser", "screenshot", path="out.png"))
    assert result.output == "out.png"
    assert ("navigate", "https://example.com") in handlers["browser"].calls


def test_missing_required_parameter_fails_gracefully(engine) -> None:
    result = engine.execute(_req("filesystem", "write"))  # no path/content
    assert result.success is False
    assert result.error is not None


def test_every_request_produces_one_audit_entry(engine, tmp_path) -> None:
    engine.execute(_req("clipboard", "set", text="x"))
    engine.execute(_req("desktop", "click", x=1, y=1))

    lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    rows = [json.loads(line) for line in lines]
    assert rows[0]["category"] == "clipboard"
    assert rows[1]["category"] == "desktop"


def test_denied_request_is_still_audited(handlers, tmp_path) -> None:
    deny_all = PermissionsConfig(default_policy="deny", rules=[])
    engine = ExecutionEngine(
        filesystem=handlers["filesystem"],
        terminal=handlers["terminal"],
        desktop=handlers["desktop"],
        application=handlers["application"],
        clipboard=handlers["clipboard"],
        screenshot=handlers["screenshot"],
        window=handlers["window"],
        browser=handlers["browser"],
        permissions=deny_all,
        audit_log_path=tmp_path / "audit.jsonl",
    )
    engine.execute(_req("filesystem", "write", path="a.md", content="hi"))

    rows = [json.loads(line) for line in (tmp_path / "audit.jsonl").read_text().splitlines()]
    assert rows[0]["allowed"] is False


def test_succeeded_event_published_on_success(handlers, permissive_permissions, tmp_path) -> None:
    events = EventBus()
    received: list[dict] = []
    events.subscribe("execution.succeeded", lambda e: received.append(e.payload))

    engine = ExecutionEngine(
        filesystem=handlers["filesystem"],
        terminal=handlers["terminal"],
        desktop=handlers["desktop"],
        application=handlers["application"],
        clipboard=handlers["clipboard"],
        screenshot=handlers["screenshot"],
        window=handlers["window"],
        browser=handlers["browser"],
        permissions=permissive_permissions,
        audit_log_path=tmp_path / "audit.jsonl",
        events=events,
    )
    engine.execute(_req("clipboard", "set", text="x"))

    assert len(received) == 1
    assert received[0]["category"] == "clipboard"


def test_denied_event_published_on_denial(handlers, tmp_path) -> None:
    events = EventBus()
    received: list[str] = []
    events.subscribe("execution.denied", lambda e: received.append(e.payload))

    deny_all = PermissionsConfig(default_policy="deny", rules=[])
    engine = ExecutionEngine(
        filesystem=handlers["filesystem"],
        terminal=handlers["terminal"],
        desktop=handlers["desktop"],
        application=handlers["application"],
        clipboard=handlers["clipboard"],
        screenshot=handlers["screenshot"],
        window=handlers["window"],
        browser=handlers["browser"],
        permissions=deny_all,
        audit_log_path=tmp_path / "audit.jsonl",
        events=events,
    )
    engine.execute(_req("filesystem", "write", path="a.md", content="hi"))

    assert len(received) == 1
