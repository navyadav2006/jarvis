"""Plain data types for the Desktop Execution Engine.

Independent of orchestrator/'s AutomationAction/AutomationResult (same
"core never depends on orchestrator" rule core/memory/types.py and
core/vault/types.py already follow) — orchestrator/execution_adapter.py
is the one place that translates between the two.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class ActionCategory(StrEnum):
    FILESYSTEM = "filesystem"
    TERMINAL = "terminal"
    DESKTOP = "desktop"
    APPLICATION = "application"
    CLIPBOARD = "clipboard"
    SCREENSHOT = "screenshot"
    WINDOW = "window"
    BROWSER = "browser"


@dataclass(frozen=True)
class ExecutionRequest:
    """One action to perform, regardless of who asked for it — Claude
    Cowork (via orchestrator/execution_adapter.py) or anything else
    that resolves ExecutionEngine directly.
    """

    category: ActionCategory
    action: str
    parameters: dict[str, Any] = field(default_factory=dict)
    requested_by: str = "unknown"


@dataclass(frozen=True)
class ExecutionResult:
    success: bool
    output: Any = None
    error: str | None = None


@dataclass(frozen=True)
class AuditEntry:
    """One row of the execution audit trail (audit.py) — every request
    ExecutionEngine.execute() ever handles gets exactly one of these,
    whether it was allowed, denied, or raised.
    """

    timestamp: datetime
    category: str
    action: str
    requested_by: str
    parameters: dict[str, Any]
    allowed: bool
    success: bool
    output: str | None
    error: str | None
    duration_seconds: float
