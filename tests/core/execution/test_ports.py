from __future__ import annotations

import sys

import pytest

from jarvis.core.exceptions import ExecutionBackendUnavailableError
from jarvis.core.execution.clipboard import PyperclipClipboard
from jarvis.core.execution.desktop import PyAutoGuiDesktopAutomation
from jarvis.core.execution.ports import (
    ApplicationPort,
    ClipboardPort,
    DesktopAutomationPort,
    NullApplicationPort,
    NullClipboardPort,
    NullDesktopAutomationPort,
    NullScreenshotPort,
    NullTerminalPort,
    NullWindowPort,
    ScreenshotPort,
    TerminalPort,
    WindowPort,
)
from jarvis.core.execution.screenshot import PillowScreenshotter
from jarvis.core.execution.window import PyGetWindowManager


@pytest.mark.parametrize(
    ("null_cls", "protocol"),
    [
        (NullTerminalPort, TerminalPort),
        (NullDesktopAutomationPort, DesktopAutomationPort),
        (NullApplicationPort, ApplicationPort),
        (NullClipboardPort, ClipboardPort),
        (NullScreenshotPort, ScreenshotPort),
        (NullWindowPort, WindowPort),
    ],
)
def test_null_port_satisfies_its_protocol(null_cls, protocol) -> None:
    assert isinstance(null_cls(), protocol)


def test_null_terminal_raises_backend_unavailable() -> None:
    with pytest.raises(ExecutionBackendUnavailableError):
        NullTerminalPort().run("echo", [], timeout=1.0)


def test_null_desktop_automation_raises_on_every_method() -> None:
    port = NullDesktopAutomationPort()
    with pytest.raises(ExecutionBackendUnavailableError):
        port.click(0, 0)
    with pytest.raises(ExecutionBackendUnavailableError):
        port.type_text("x")
    with pytest.raises(ExecutionBackendUnavailableError):
        port.key_press("enter")


def test_null_clipboard_raises_on_get_and_set() -> None:
    port = NullClipboardPort()
    with pytest.raises(ExecutionBackendUnavailableError):
        port.get()
    with pytest.raises(ExecutionBackendUnavailableError):
        port.set("x")


def test_null_screenshot_raises() -> None:
    with pytest.raises(ExecutionBackendUnavailableError):
        NullScreenshotPort().capture("out.png")


def test_null_window_raises_on_every_method() -> None:
    port = NullWindowPort()
    for call in (port.list_windows, lambda: port.focus("x"), lambda: port.minimize("x")):
        with pytest.raises(ExecutionBackendUnavailableError):
            call()


def test_missing_pyautogui_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "pyautogui", None)
    with pytest.raises(ExecutionBackendUnavailableError):
        PyAutoGuiDesktopAutomation().click(0, 0)


def test_missing_pyperclip_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "pyperclip", None)
    with pytest.raises(ExecutionBackendUnavailableError):
        PyperclipClipboard().get()


def test_missing_pillow_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "PIL", None)
    with pytest.raises(ExecutionBackendUnavailableError):
        PillowScreenshotter().capture("out.png")


def test_missing_pygetwindow_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "pygetwindow", None)
    with pytest.raises(ExecutionBackendUnavailableError):
        PyGetWindowManager().list_windows()
