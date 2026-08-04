"""The Desktop Execution Engine (Phase 15): where Claude Cowork-requested
actions actually run, across seven categories — filesystem, terminal,
desktop automation, application management, clipboard, screenshots, and
window management.

`ExecutionEngine.execute()` is the single entry point: it checks
`permissions.yaml` before doing anything (Phase 3's `PermissionsConfig`
gets its first real caller here), dispatches to a category handler, and
records exactly one `AuditEntry` (audit.py) per attempt — allowed or
not, succeeded or not. `orchestrator/execution_adapter.py` bridges this
module's own types to `orchestrator.ports.AutomationPort`, the same
"core never depends on orchestrator" bridge pattern
`orchestrator/memory_adapter.py` already established.

Filesystem/terminal/application handlers are real and dependency-free
(reusing FilesystemPort, and stdlib `subprocess`). Desktop automation,
clipboard, screenshots, and window management each lazily import an
optional third-party library (the 'desktop' extra) — see each module's
own docstring.
"""

from __future__ import annotations

from jarvis.core.execution.application import ProcessApplicationManager
from jarvis.core.execution.audit import AuditTrail
from jarvis.core.execution.clipboard import PyperclipClipboard
from jarvis.core.execution.desktop import PyAutoGuiDesktopAutomation
from jarvis.core.execution.engine import ExecutionEngine
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
from jarvis.core.execution.terminal import SubprocessTerminal
from jarvis.core.execution.types import (
    ActionCategory,
    AuditEntry,
    ExecutionRequest,
    ExecutionResult,
)
from jarvis.core.execution.window import PyGetWindowManager

__all__ = [
    "ActionCategory",
    "ApplicationPort",
    "AuditEntry",
    "AuditTrail",
    "ClipboardPort",
    "DesktopAutomationPort",
    "ExecutionEngine",
    "ExecutionRequest",
    "ExecutionResult",
    "NullApplicationPort",
    "NullClipboardPort",
    "NullDesktopAutomationPort",
    "NullScreenshotPort",
    "NullTerminalPort",
    "NullWindowPort",
    "PillowScreenshotter",
    "ProcessApplicationManager",
    "PyAutoGuiDesktopAutomation",
    "PyGetWindowManager",
    "PyperclipClipboard",
    "ScreenshotPort",
    "SubprocessTerminal",
    "TerminalPort",
    "WindowPort",
]
