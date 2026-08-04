"""Plain data types for the Jarvis Security Manager.

Independent of core/execution/'s own types (`ExecutionRequest`, etc.)
— same "own types per module" rule every module since core/memory/ has
followed. `SecurityManager` (manager.py) is meant to sit *in front of*
`ExecutionEngine`, not replace it; the two modules don't need to share
type definitions to compose.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum


class PermissionLevel(IntEnum):
    """Ordered by risk, low to high — an `IntEnum` (not `StrEnum`,
    unlike most enums in this project) specifically so levels compare
    with `<`/`>=` (e.g. "does this action's level require
    confirmation") without a separate ranking table.
    """

    READ = 0
    WRITE = 1
    EXECUTE = 2
    ADMINISTRATOR = 3
    DANGEROUS = 4
    BLOCKED = 5

    @property
    def label(self) -> str:
        return self.name.lower()


@dataclass(frozen=True)
class SecurityRequest:
    category: str
    action: str
    requested_by: str
    path: str | None = None
    parameters: dict = field(default_factory=dict)


@dataclass(frozen=True)
class SecurityDecision:
    allowed: bool
    level: PermissionLevel
    reason: str
    required_confirmation: bool = False


@dataclass(frozen=True)
class SecurityAuditEntry:
    timestamp: datetime
    category: str
    action: str
    requested_by: str
    level: str
    allowed: bool
    reason: str
    required_confirmation: bool
