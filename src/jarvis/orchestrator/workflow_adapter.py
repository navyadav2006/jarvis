"""AutomationWorkflowActionPort: bridges core/workflow/'s
WorkflowActionPort to orchestrator.ports.AutomationPort — the same
one-way-dependency bridge pattern orchestrator/execution_adapter.py
and orchestrator/memory_adapter.py already established.

This is the concrete answer to "workflow steps must go through the
same security gate as everything else": `AutomationPort` handed to
this adapter in `main.py` is the exact same instance Cowork-originated
actions already execute through (Phase 15's `ExecutionEngineAdapter`,
gated by Phase 19's `SecurityManager`, when execution.yaml's `enabled`
is true; `NullAutomationPort` otherwise). A workflow step is executed
by calling `AutomationPort.execute()` — nothing here reaches
`ExecutionEngine` or the OS directly, so there is no second, unguarded
path for a workflow to run an action through.
"""

from __future__ import annotations

from jarvis.core.workflow.ports import WorkflowActionResult
from jarvis.orchestrator.ports import AutomationAction, AutomationPort


class AutomationWorkflowActionPort:
    """Implements core.workflow.ports.WorkflowActionPort."""

    def __init__(self, automation: AutomationPort) -> None:
        self._automation = automation

    def execute(self, action: str, parameters: dict) -> WorkflowActionResult:
        result = self._automation.execute(AutomationAction(name=action, parameters=parameters))
        return WorkflowActionResult(
            success=result.success, output=result.output, error=result.error
        )
