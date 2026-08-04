"""The Jarvis Security Manager (Phase 19): the one gate every action —
Cowork-originated or otherwise — passes through before it reaches
`ExecutionEngine` (Phase 15). Six permission levels (Read/Write/
Execute/Administrator/Dangerous/Blocked), confirmation dialogs for the
risky ones, filesystem allow/deny (reusing Phase 4's `PathGuard`),
rate limiting, durable audit logs, in-memory session history, and an
emergency shutdown that denies everything until lifted.

See `manager.py`'s module docstring for the full check order and
docs/architecture.md's Phase 19 section for how "Cowork must never
bypass the security layer" is enforced structurally, not by policy.
"""

from __future__ import annotations

from jarvis.core.security.audit import SecurityAuditTrail
from jarvis.core.security.confirmation import (
    AutoDenyConfirmation,
    CallbackConfirmation,
    ConfirmationPort,
)
from jarvis.core.security.levels import LEVELS, PERMISSION_SCOPES, level_for, scope_for
from jarvis.core.security.manager import SecurityManager
from jarvis.core.security.rate_limiter import RateLimiter
from jarvis.core.security.session_history import SessionHistory
from jarvis.core.security.types import (
    PermissionLevel,
    SecurityAuditEntry,
    SecurityDecision,
    SecurityRequest,
)

__all__ = [
    "LEVELS",
    "PERMISSION_SCOPES",
    "AutoDenyConfirmation",
    "CallbackConfirmation",
    "ConfirmationPort",
    "PermissionLevel",
    "RateLimiter",
    "SecurityAuditEntry",
    "SecurityAuditTrail",
    "SecurityDecision",
    "SecurityManager",
    "SecurityRequest",
    "SessionHistory",
    "level_for",
    "scope_for",
]
