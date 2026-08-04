"""Ports the Workflow engine depends on: running one step's action, and
persisting workflows/runs. `Protocol`s (structural typing), matching
every other port in `core/` — an implementation doesn't need to import
this module or subclass anything.

No Null defaults here: `WorkflowActionPort`'s real implementation
(`orchestrator/workflow_adapter.py`) just delegates to whatever
`AutomationPort` is already wired (real or `NullAutomationPort`), so a
workflow step against an unconfigured automation backend fails the
same explicit way any other automation action already does — a second
Null Object here would just duplicate that behavior. `WorkflowStorePort`
has one real implementation (`store.py`'s `SqliteWorkflowStore`) and no
Null default, the same "always real" choice `SecurityManager`'s
`PathGuard` reuse and `PlanningEngine` made — a workflow engine with
nowhere to persist workflows isn't a meaningful degraded mode.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from jarvis.core.workflow.types import Workflow, WorkflowRun


@dataclass(frozen=True)
class WorkflowActionResult:
    success: bool
    output: Any = None
    error: str | None = None


@runtime_checkable
class WorkflowActionPort(Protocol):
    def execute(self, action: str, parameters: dict) -> WorkflowActionResult:
        """Run one workflow step's dotted "category.action" and report
        the outcome. Implementations MUST route through whatever
        already gates real automation (Phase 19's SecurityManager) —
        see orchestrator/workflow_adapter.py.
        """
        ...


@runtime_checkable
class WorkflowStorePort(Protocol):
    def save_workflow(self, workflow: Workflow) -> None: ...

    def get_workflow(self, workflow_id: str) -> Workflow | None: ...

    def list_workflows(self) -> list[Workflow]: ...

    def delete_workflow(self, workflow_id: str) -> bool: ...

    def save_run(self, run: WorkflowRun) -> None: ...

    def get_run(self, run_id: str) -> WorkflowRun | None: ...

    def list_runs(
        self, *, workflow_id: str | None = None, limit: int = 50
    ) -> list[WorkflowRun]: ...
