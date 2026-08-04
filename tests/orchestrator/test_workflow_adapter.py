from __future__ import annotations

from jarvis.core.workflow.ports import WorkflowActionResult
from jarvis.orchestrator.ports import AutomationAction, AutomationResult
from jarvis.orchestrator.workflow_adapter import AutomationWorkflowActionPort


class FakeAutomationPort:
    def __init__(self, result: AutomationResult | None = None) -> None:
        self.received: list[AutomationAction] = []
        self.result = result or AutomationResult(success=True, output="ok")

    def execute(self, action: AutomationAction) -> AutomationResult:
        self.received.append(action)
        return self.result


def test_execute_delegates_to_the_wrapped_automation_port() -> None:
    automation = FakeAutomationPort()
    adapter = AutomationWorkflowActionPort(automation)

    result = adapter.execute("filesystem.write", {"path": "x"})

    expected = AutomationAction(name="filesystem.write", parameters={"path": "x"})
    assert automation.received[0] == expected
    assert result == WorkflowActionResult(success=True, output="ok", error=None)


def test_execute_surfaces_automation_failure() -> None:
    automation = FakeAutomationPort(AutomationResult(success=False, error="denied"))
    adapter = AutomationWorkflowActionPort(automation)

    result = adapter.execute("filesystem.delete", {})

    assert result.success is False
    assert result.error == "denied"


def test_workflow_step_execution_goes_through_the_same_automation_port_as_cowork() -> None:
    # This is the concrete guarantee: a workflow step is executed by
    # calling AutomationPort.execute() -- the exact same call Cowork-
    # originated actions make via ExecutionEngineAdapter -- so whatever
    # gates that (SecurityManager) gates workflow steps too, with no
    # second path.
    automation = FakeAutomationPort()
    adapter = AutomationWorkflowActionPort(automation)
    adapter.execute("clipboard.get", {})
    assert len(automation.received) == 1
