from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core.config.permissions_config import PermissionRule, PermissionsConfig
from jarvis.core.execution.engine import ExecutionEngine
from jarvis.core.filesystem.port import FileOperationResult


class FakeFilesystemPort:
    def __init__(self) -> None:
        self.files: dict[str, str] = {}
        self.calls: list[tuple[str, tuple]] = []

    def read(self, path) -> str:
        self.calls.append(("read", (path,)))
        return self.files[str(path)]

    def write(self, path, content: str, *, confirmed: bool = False) -> FileOperationResult:
        self.calls.append(("write", (path, content)))
        self.files[str(path)] = content
        return FileOperationResult(operation="write", success=True, path=Path(path))

    def copy(self, source, destination, *, confirmed: bool = False) -> FileOperationResult:
        self.calls.append(("copy", (source, destination)))
        return FileOperationResult(
            operation="copy", success=True, path=Path(source), destination=Path(destination)
        )

    def move(self, source, destination, *, confirmed: bool = False) -> FileOperationResult:
        self.calls.append(("move", (source, destination)))
        return FileOperationResult(
            operation="move", success=True, path=Path(source), destination=Path(destination)
        )

    def rename(self, path, new_name: str, *, confirmed: bool = False) -> FileOperationResult:
        self.calls.append(("rename", (path, new_name)))
        return FileOperationResult(operation="rename", success=True, path=Path(path))

    def delete(self, path, *, confirmed: bool = False) -> FileOperationResult:
        self.calls.append(("delete", (path,)))
        return FileOperationResult(operation="delete", success=True, path=Path(path))

    def search(self, directory, pattern: str, *, recursive: bool = True) -> list[Path]:
        self.calls.append(("search", (directory, pattern)))
        return []


class FakeTerminal:
    def __init__(self, result: tuple[int, str, str] = (0, "ok", "")) -> None:
        self.result = result
        self.calls: list[tuple[str, list[str]]] = []

    def run(self, command: str, args: list[str], *, timeout: float) -> tuple[int, str, str]:
        self.calls.append((command, args))
        return self.result


class FakeDesktop:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def click(self, x: int, y: int) -> None:
        self.calls.append(("click", x, y))

    def type_text(self, text: str) -> None:
        self.calls.append(("type_text", text))

    def key_press(self, key: str) -> None:
        self.calls.append(("key_press", key))


class FakeApplication:
    def __init__(self) -> None:
        self.launched: list[tuple[str, list[str]]] = []
        self.closed: list[str] = []

    def launch(self, path: str, args: list[str]) -> int:
        self.launched.append((path, args))
        return 4242

    def close(self, process_name: str) -> bool:
        self.closed.append(process_name)
        return True


class FakeClipboard:
    def __init__(self) -> None:
        self.value = ""

    def get(self) -> str:
        return self.value

    def set(self, text: str) -> None:
        self.value = text


class FakeScreenshot:
    def capture(self, path: str) -> str:
        return path


class FakeWindow:
    def list_windows(self) -> list[str]:
        return ["Window A", "Window B"]

    def focus(self, title: str) -> bool:
        return title == "Window A"

    def minimize(self, title: str) -> bool:
        return title == "Window A"

    def maximize(self, title: str) -> bool:
        return title == "Window A"


class FakeBrowser:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def search(self, query: str):
        self.calls.append(("search", query))
        return []

    def navigate(self, url: str):
        self.calls.append(("navigate", url))
        return {"url": url, "title": "Fake Page"}

    def fill_form(self, fields: dict, *, submit: bool = False):
        self.calls.append(("fill_form", fields, submit))
        return {"success": True}

    def authenticate(self, url: str, **kwargs):
        self.calls.append(("authenticate", url))
        return {"success": True}

    def download(self, url: str, destination: str) -> str:
        self.calls.append(("download", url, destination))
        return destination

    def screenshot(self, path: str) -> str:
        self.calls.append(("screenshot", path))
        return path

    def summarize_page(self):
        self.calls.append(("summarize_page",))
        return {"title": "Fake Page"}

    def close(self) -> None:
        self.calls.append(("close",))


@pytest.fixture
def permissive_permissions() -> PermissionsConfig:
    return PermissionsConfig(
        default_policy="deny",
        rules=[
            PermissionRule(
                plugin="cowork",
                allow=[
                    "filesystem.read",
                    "filesystem.write",
                    "terminal.run",
                    "automation.mouse",
                    "automation.keyboard",
                    "application.launch",
                    "application.close",
                    "clipboard.read",
                    "clipboard.write",
                    "browser.control",
                    "screenshot.capture",
                    "window.read",
                    "window.write",
                ],
            )
        ],
    )


@pytest.fixture
def handlers():
    return {
        "filesystem": FakeFilesystemPort(),
        "terminal": FakeTerminal(),
        "desktop": FakeDesktop(),
        "application": FakeApplication(),
        "clipboard": FakeClipboard(),
        "screenshot": FakeScreenshot(),
        "window": FakeWindow(),
        "browser": FakeBrowser(),
    }


@pytest.fixture
def engine(handlers, permissive_permissions, tmp_path: Path) -> ExecutionEngine:
    return ExecutionEngine(
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
    )
