"""SecurityManager: the Jarvis Security Manager (Phase 19) — the one
gate every action must pass through, regardless of who's asking.

Six checks run in order, cheapest/most-global first; the first one
that fails wins and nothing further runs:

    1. Emergency shutdown — if active, everything is denied.
    2. Permission level — BLOCKED (unclassified) actions are denied
       outright (levels.py).
    3. Rate limiting — per (requester, level) sliding window.
    4. Filesystem allowlist/denylist — reuses Phase 4's `PathGuard`
       for any request carrying a `path`, rather than reimplementing
       it; "filesystem allowlists"/"denylists" already exist, this
       phase's job is making every path-bearing security decision
       consult them, not rebuilding them.
    5. Permission scope — reuses Phase 3's `PermissionsConfig.is_allowed()`,
       the same mechanism ExecutionEngine (Phase 15) and PluginLoader
       (Phase 18) already enforce.
    6. Confirmation — DANGEROUS/ADMINISTRATOR levels (configurable)
       require an explicit yes via ConfirmationPort before proceeding.

Every call to `authorize()` — allowed or denied — is recorded to both
the durable `SecurityAuditTrail` and the in-memory per-requester
`SessionHistory`.

"Claude Cowork must never bypass the security layer" is structural,
not a policy statement: `orchestrator/execution_adapter.py`'s
`ExecutionEngineAdapter` is the *only* path from a Cowork-originated
`AutomationAction` to real execution (Phase 9 established this, and
nothing since has added a second path), and it now calls
`SecurityManager.authorize()` before ever calling
`ExecutionEngine.execute()` — a denial here means `ExecutionEngine` is
never even invoked, the same "check before dispatch" shape
`ExecutionEngine` itself already uses for `PermissionsConfig`.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from jarvis.core.config._paths import PROJECT_ROOT
from jarvis.core.config.filesystem_config import FilesystemConfig
from jarvis.core.config.permissions_config import PermissionsConfig
from jarvis.core.config.security_config import SecurityConfig
from jarvis.core.events import EventBus
from jarvis.core.exceptions import FilesystemAccessError
from jarvis.core.filesystem.path_guard import PathGuard
from jarvis.core.security.audit import SecurityAuditTrail
from jarvis.core.security.confirmation import ConfirmationPort
from jarvis.core.security.levels import level_for, scope_for
from jarvis.core.security.rate_limiter import RateLimiter
from jarvis.core.security.session_history import SessionHistory
from jarvis.core.security.types import (
    PermissionLevel,
    SecurityAuditEntry,
    SecurityDecision,
    SecurityRequest,
)

logger = logging.getLogger(__name__)

_RATE_LIMITED_LEVELS = (
    PermissionLevel.READ,
    PermissionLevel.WRITE,
    PermissionLevel.EXECUTE,
    PermissionLevel.DANGEROUS,
    PermissionLevel.ADMINISTRATOR,
)


class SecurityManager:
    def __init__(
        self,
        config: SecurityConfig,
        *,
        filesystem_config: FilesystemConfig,
        permissions: PermissionsConfig,
        confirmation: ConfirmationPort,
        events: EventBus | None = None,
        root: Path = PROJECT_ROOT,
    ) -> None:
        self._config = config
        self._permissions = permissions
        self._confirmation = confirmation
        self._events = events
        self._path_guard = PathGuard(filesystem_config, root=root)
        rate_limits = config.rate_limits
        self._rate_limiter = RateLimiter(
            {
                PermissionLevel.READ: rate_limits.read_per_minute,
                PermissionLevel.WRITE: rate_limits.write_per_minute,
                PermissionLevel.EXECUTE: rate_limits.execute_per_minute,
                PermissionLevel.DANGEROUS: rate_limits.dangerous_per_minute,
                PermissionLevel.ADMINISTRATOR: rate_limits.administrator_per_minute,
            }
        )
        self._audit = SecurityAuditTrail(config.audit_log_path)
        self._session_history = SessionHistory(limit=config.session_history_limit)
        self._confirmation_levels = {
            PermissionLevel[name.upper()] for name in config.confirmation_required_levels
        }
        self._shutdown = False
        self._shutdown_reason: str | None = None

    def authorize(self, request: SecurityRequest) -> SecurityDecision:
        if self.is_shutdown:
            reason = f"emergency shutdown active: {self._shutdown_reason}"
            return self._deny(request, PermissionLevel.BLOCKED, reason)

        level = level_for(request.category, request.action)

        if level == PermissionLevel.BLOCKED:
            return self._deny(request, level, "action is not recognized, or is explicitly blocked")

        if level in _RATE_LIMITED_LEVELS and not self._rate_limiter.allow(
            request.requested_by, level
        ):
            self._publish("security.rate_limited", request, level)
            return self._deny(request, level, f"rate limit exceeded for {level.label} actions")

        if request.path is not None:
            try:
                self._path_guard.check(request.path)
            except FilesystemAccessError as exc:
                return self._deny(request, level, str(exc))

        # Reuse ExecutionEngine's exact scope-string mapping (see
        # levels.py's module docstring for the bug this fixes); fall
        # back to the raw "category.action" for actions outside its
        # dispatch table (e.g. "plugin.install"), which have no
        # competing definition to disagree with.
        scope = scope_for(request.category, request.action)
        if scope is None:
            scope = f"{request.category}.{request.action}"
        if not self._permissions.is_allowed(request.requested_by, scope):
            return self._deny(
                request, level, f"permissions.yaml denies {scope!r} to {request.requested_by!r}"
            )

        requires_confirmation = level in self._confirmation_levels
        if requires_confirmation:
            prompt = f"Allow {request.requested_by!r} to perform {scope!r} ({level.label})?"
            if not self._confirmation.confirm(prompt):
                self._publish("security.confirmation_denied", request, level)
                return self._deny(
                    request, level, "confirmation was declined", required_confirmation=True
                )

        decision = SecurityDecision(
            allowed=True, level=level, reason="allowed", required_confirmation=requires_confirmation
        )
        self._record(request, decision)
        return decision

    # -- emergency shutdown ---------------------------------------------------

    def trigger_emergency_shutdown(self, reason: str) -> None:
        self._shutdown_reason = reason
        logger.critical("EMERGENCY SHUTDOWN triggered: %s", reason)
        self._shutdown = True
        if self._events is not None:
            self._events.publish(
                "security.emergency_shutdown", {"reason": reason}, source="security_manager"
            )

    def resume(self, reason: str = "") -> None:
        logger.warning("Emergency shutdown lifted: %s", reason)
        self._shutdown = False
        self._shutdown_reason = None
        if self._events is not None:
            self._events.publish("security.resumed", {"reason": reason}, source="security_manager")

    @property
    def is_shutdown(self) -> bool:
        return self._shutdown

    # -- introspection ---------------------------------------------------------

    def session_history_for(self, requested_by: str) -> list[SecurityDecision]:
        return self._session_history.for_requester(requested_by)

    def audit_log(self) -> list[dict]:
        return self._audit.read_all()

    # -- internals -----------------------------------------------------------

    def _deny(
        self,
        request: SecurityRequest,
        level: PermissionLevel,
        reason: str,
        *,
        required_confirmation: bool = False,
    ) -> SecurityDecision:
        decision = SecurityDecision(
            allowed=False, level=level, reason=reason, required_confirmation=required_confirmation
        )
        self._record(request, decision)
        return decision

    def _record(self, request: SecurityRequest, decision: SecurityDecision) -> None:
        self._session_history.record(request.requested_by, decision)
        entry = SecurityAuditEntry(
            timestamp=datetime.now(UTC),
            category=request.category,
            action=request.action,
            requested_by=request.requested_by,
            level=decision.level.label,
            allowed=decision.allowed,
            reason=decision.reason,
            required_confirmation=decision.required_confirmation,
        )
        self._audit.record(entry)

    def _publish(self, name: str, request: SecurityRequest, level: PermissionLevel) -> None:
        if self._events is not None:
            self._events.publish(
                name,
                {
                    "category": request.category,
                    "action": request.action,
                    "requested_by": request.requested_by,
                    "level": level.label,
                },
                source="security_manager",
            )
