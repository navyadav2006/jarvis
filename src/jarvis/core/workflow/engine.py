"""WorkflowEngine: creates, edits, and runs `Workflow`s ("multi-step
automation", "workflow editing", "workflow history"). Steps execute
wave-by-wave in dependency order (`dependencies.topological_waves()`);
each step's default rule is "run iff every dependency SUCCEEDED",
overridable per-step via an explicit `WorkflowCondition`
("conditional execution") — see `types.py`'s `WorkflowStep.condition`
docstring for why a condition may only reference an actual dependency.

`run_workflow()` is synchronous — it runs to completion on the calling
thread, the same "the engine does the work, the caller decides
sync/async" split `core/execution/`'s `ExecutionEngine.execute()` uses.
"Background jobs" is `WorkflowRunner`'s job (runner.py): a thin
worker-pool wrapper that calls this method off a queue, not a second
execution path.

Nothing here calls Cowork or touches the OS directly — steps run via
the injected `WorkflowActionPort`, which in production
(`orchestrator/workflow_adapter.py`) delegates to the same
`AutomationPort` every other automation action already goes through,
including Phase 19's `SecurityManager` gate. This mirrors "Cowork
proposes, Jarvis executes" (Phase 9) and "PlanningEngine tracks, the
caller executes" (Phase 17): here it's "WorkflowEngine tracks and
sequences, the action port executes."
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from jarvis.core.cowork.models import CoworkTaskResponse
from jarvis.core.events import EventBus
from jarvis.core.exceptions import WorkflowNotFoundError
from jarvis.core.workflow.conditions import evaluate_condition
from jarvis.core.workflow.dependencies import topological_waves
from jarvis.core.workflow.ports import WorkflowActionPort, WorkflowStorePort
from jarvis.core.workflow.types import (
    Workflow,
    WorkflowRun,
    WorkflowSchedule,
    WorkflowStatus,
    WorkflowStep,
    WorkflowStepResult,
    WorkflowStepStatus,
    WorkflowTrigger,
)
from jarvis.core.workflow.validation import validate_schedule, validate_steps

logger = logging.getLogger(__name__)


class WorkflowEngine:
    def __init__(
        self,
        store: WorkflowStorePort,
        action_port: WorkflowActionPort,
        *,
        events: EventBus | None = None,
    ) -> None:
        self._store = store
        self._action_port = action_port
        self._events = events

    # -- workflow editing (CRUD) ----------------------------------------------

    def create_workflow(
        self,
        name: str,
        steps: list[WorkflowStep],
        *,
        description: str = "",
        schedule: WorkflowSchedule | None = None,
        enabled: bool = True,
        created_by: str = "user",
    ) -> Workflow:
        validate_steps(steps)
        validate_schedule(schedule)
        workflow = Workflow(
            id=uuid.uuid4().hex,
            name=name,
            steps=steps,
            description=description,
            schedule=schedule,
            enabled=enabled,
            created_by=created_by,
        )
        self._store.save_workflow(workflow)
        self._publish("workflow.created", workflow)
        return workflow

    def update_workflow(
        self,
        workflow_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        steps: list[WorkflowStep] | None = None,
        schedule: WorkflowSchedule | None = ...,
        enabled: bool | None = None,
    ) -> Workflow:
        """`schedule=...` (the Ellipsis sentinel, not a default of None)
        means "leave unchanged" — None is a valid value meaning "remove
        the schedule", so a real default couldn't tell the two apart.
        """
        workflow = self.get_workflow(workflow_id)
        if name is not None:
            workflow.name = name
        if description is not None:
            workflow.description = description
        if steps is not None:
            validate_steps(steps)
            workflow.steps = steps
        if schedule is not ...:
            validate_schedule(schedule)
            workflow.schedule = schedule
        if enabled is not None:
            workflow.enabled = enabled
        workflow.updated_at = datetime.now(UTC)
        self._store.save_workflow(workflow)
        self._publish("workflow.updated", workflow)
        return workflow

    def delete_workflow(self, workflow_id: str) -> None:
        if not self._store.delete_workflow(workflow_id):
            raise WorkflowNotFoundError(f"no workflow {workflow_id!r}")
        if self._events is not None:
            self._events.publish(
                "workflow.deleted", {"workflow_id": workflow_id}, source="workflow_engine"
            )

    def get_workflow(self, workflow_id: str) -> Workflow:
        workflow = self._store.get_workflow(workflow_id)
        if workflow is None:
            raise WorkflowNotFoundError(f"no workflow {workflow_id!r}")
        return workflow

    def list_workflows(self) -> list[Workflow]:
        return self._store.list_workflows()

    # -- Cowork generates the plan, Jarvis owns the workflow -------------------

    def workflow_from_cowork_response(
        self, response: CoworkTaskResponse, *, created_by: str = "cowork"
    ) -> Workflow:
        """Turn Cowork's plan into a saved, runnable Workflow — "Claude
        Cowork should generate workflow plans, Jarvis executes them".
        Sequential by step order (each step depends on the one before
        it), same default `PlanningEngine.plan_from_cowork_response()`
        uses. "respond"-type steps (no automation to perform) are
        dropped — a workflow is a sequence of *actions*, so nothing is
        lost by leaving prose-only steps out of it.
        """
        steps: list[WorkflowStep] = []
        previous_id: str | None = None
        for step in response.steps:
            if step.action_type != "automation" or step.automation is None:
                continue
            step_id = str(step.step_id)
            steps.append(
                WorkflowStep(
                    id=step_id,
                    name=step.description,
                    action=step.automation.name,
                    parameters=dict(step.automation.parameters),
                    depends_on=(previous_id,) if previous_id is not None else (),
                )
            )
            previous_id = step_id
        return self.create_workflow(name=response.summary, steps=steps, created_by=created_by)

    # -- execution ("multi-step automation") -----------------------------------

    def run_workflow(
        self, workflow_id: str, *, trigger: WorkflowTrigger = WorkflowTrigger.MANUAL
    ) -> WorkflowRun:
        workflow = self.get_workflow(workflow_id)
        run = WorkflowRun(
            id=uuid.uuid4().hex,
            workflow_id=workflow_id,
            trigger=trigger,
            status=WorkflowStatus.RUNNING,
            started_at=datetime.now(UTC),
        )
        for step in workflow.steps:
            run.step_results[step.id] = WorkflowStepResult(step_id=step.id)
        self._store.save_run(run)
        self._publish("workflow.run_started", workflow, run)

        by_id = {step.id: step for step in workflow.steps}
        for wave in topological_waves(workflow.steps):
            for step_id in wave:
                self._run_step(workflow, run, by_id[step_id])
            self._store.save_run(run)

        run.status = (
            WorkflowStatus.FAILED
            if any(r.status == WorkflowStepStatus.FAILED for r in run.step_results.values())
            else WorkflowStatus.SUCCEEDED
        )
        run.finished_at = datetime.now(UTC)
        self._store.save_run(run)
        self._publish("workflow.run_finished", workflow, run)
        return run

    def list_runs(self, workflow_id: str | None = None, *, limit: int = 50) -> list[WorkflowRun]:
        return self._store.list_runs(workflow_id=workflow_id, limit=limit)

    # -- visualization --------------------------------------------------------

    def render_mermaid(self, workflow_id: str, *, run: WorkflowRun | None = None) -> str:
        from jarvis.core.workflow.visualization import to_mermaid

        return to_mermaid(self.get_workflow(workflow_id), run)

    # -- internals -------------------------------------------------------------

    def _run_step(self, workflow: Workflow, run: WorkflowRun, step: WorkflowStep) -> None:
        result = run.step_results[step.id]
        should_run = self._should_run(step, run)
        if not should_run:
            result.status = WorkflowStepStatus.SKIPPED
            result.finished_at = datetime.now(UTC)
            return

        result.status = WorkflowStepStatus.RUNNING
        result.started_at = datetime.now(UTC)
        self._publish("workflow.step_started", workflow, run, step)

        try:
            outcome = self._action_port.execute(step.action, step.parameters)
        except Exception as exc:
            logger.exception("Unhandled error running workflow step %s.%s", workflow.id, step.id)
            result.status = WorkflowStepStatus.FAILED
            result.error = f"unexpected error: {exc}"
        else:
            if outcome.success:
                result.status = WorkflowStepStatus.SUCCEEDED
                result.output = outcome.output
            else:
                result.status = WorkflowStepStatus.FAILED
                result.error = outcome.error

        result.finished_at = datetime.now(UTC)
        self._publish("workflow.step_finished", workflow, run, step)

    def _should_run(self, step: WorkflowStep, run: WorkflowRun) -> bool:
        if step.condition is not None:
            return evaluate_condition(step.condition, run.step_results)
        deps = [run.step_results[d] for d in step.depends_on]
        return all(d.status == WorkflowStepStatus.SUCCEEDED for d in deps)

    def _publish(
        self,
        name: str,
        workflow: Workflow,
        run: WorkflowRun | None = None,
        step: WorkflowStep | None = None,
    ) -> None:
        if self._events is None:
            return
        payload: dict = {"workflow_id": workflow.id, "workflow_name": workflow.name}
        if run is not None:
            payload.update({"run_id": run.id, "status": run.status.value})
        if step is not None:
            result = run.step_results[step.id] if run is not None else None
            payload.update(
                {"step_id": step.id, "step_status": result.status.value if result else None}
            )
        self._events.publish(name, payload, source="workflow_engine")
