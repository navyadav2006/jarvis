"""ExecutionEngineAdapter: bridges core/execution/'s ExecutionEngine to
orchestrator.ports.AutomationPort's shape — the same one-way-dependency
bridge pattern orchestrator/memory_adapter.py already established for
core/memory/.

`AutomationAction.name` is a dotted `"category.action"` string (e.g.
`"filesystem.write"`, `"desktop.click"`) — this adapter splits it and
maps the category half onto core/execution/types.py's `ActionCategory`.
`requested_by` is fixed at construction time (typically
`execution.yaml`'s `default_requester`, e.g. `"cowork"`) since
AutomationAction itself carries no notion of who's asking — every
action routed through one Orchestrator+AutomationPort pairing shares
one identity for permission-checking purposes.

Phase 19 adds an optional `security: SecurityManager` gate, checked
*before* `ExecutionEngine.execute()` is ever called. This is the
concrete answer to "Claude Cowork must never bypass the security
layer": this adapter is the only path from a Cowork-originated
`AutomationAction` to real execution (Phase 9), so a denial here means
`ExecutionEngine` — and everything real it can do — is never reached
at all, not merely double-checked afterward.
"""

from __future__ import annotations

from jarvis.core.execution.engine import ExecutionEngine
from jarvis.core.execution.types import ActionCategory, ExecutionRequest
from jarvis.core.security.manager import SecurityManager
from jarvis.core.security.types import SecurityRequest
from jarvis.orchestrator.ports import AutomationAction, AutomationResult


class ExecutionEngineAdapter:
    """Implements orchestrator.ports.AutomationPort."""

    def __init__(
        self,
        engine: ExecutionEngine,
        *,
        requested_by: str = "cowork",
        security: SecurityManager | None = None,
    ) -> None:
        self._engine = engine
        self._requested_by = requested_by
        self._security = security

    def execute(self, action: AutomationAction) -> AutomationResult:
        try:
            category_name, _, bare_action = action.name.partition(".")
            category = ActionCategory(category_name)
        except ValueError:
            return AutomationResult(
                success=False, error=f"malformed or unknown action name: {action.name!r}"
            )

        if self._security is not None:
            decision = self._security.authorize(
                SecurityRequest(
                    category=category_name,
                    action=bare_action,
                    requested_by=self._requested_by,
                    path=action.parameters.get("path"),
                    parameters=action.parameters,
                )
            )
            if not decision.allowed:
                return AutomationResult(success=False, error=decision.reason)

        request = ExecutionRequest(
            category=category,
            action=bare_action,
            parameters=action.parameters,
            requested_by=self._requested_by,
        )
        result = self._engine.execute(request)
        return AutomationResult(success=result.success, output=result.output, error=result.error)
