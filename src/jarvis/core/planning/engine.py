"""PlanningEngine: the Planning Engine (Phase 17) — reusable task
decomposition, dependency estimation, parallel-work detection,
collaborator assignment, progress tracking, and retry, all in one
place so any future feature needing a multi-step plan uses this
instead of reinventing it ("the planner must be reusable for every
future feature").

Nothing here calls Cowork, executes an action, or touches the OS —
`PlanningEngine` only produces and tracks `ExecutionPlan`s; running a
task is entirely the caller's job (typically: for each ready task,
submit it to `CoworkWorkspace`/`ExecutionEngine`, then report the
outcome back via `mark_done()`/`mark_failed()`). This mirrors the
"Cowork proposes, Jarvis executes" boundary from Phase 9/15 — here it's
"PlanningEngine tracks, the caller executes."
"""

from __future__ import annotations

import logging
import uuid

from jarvis.core.config.planning_config import PlanningConfig
from jarvis.core.cowork.models import CoworkTaskResponse
from jarvis.core.cowork.workspace import select_role
from jarvis.core.events import EventBus
from jarvis.core.planning.decomposition import decompose_request
from jarvis.core.planning.dependencies import estimate_sequential_dependencies, topological_waves
from jarvis.core.planning.types import ExecutionPlan, PlanTask, TaskStatus

logger = logging.getLogger(__name__)


class PlanningEngine:
    def __init__(self, config: PlanningConfig, *, events: EventBus | None = None) -> None:
        self._config = config
        self._events = events

    # -- plan creation ---------------------------------------------------

    def create_plan(
        self, request: str, *, task_descriptions: list[str] | None = None
    ) -> ExecutionPlan:
        """Break `request` into tasks (or use `task_descriptions` if the
        caller already has them — e.g. from Cowork's Planner
        collaborator), estimate dependencies, and assign a collaborator
        to each.
        """
        descriptions = (
            task_descriptions if task_descriptions is not None else decompose_request(request)
        )
        if not descriptions:
            descriptions = [request]

        dependency_sets = estimate_sequential_dependencies(descriptions)
        tasks = [
            PlanTask(
                id=str(i),
                description=description,
                collaborator=select_role(description),
                depends_on=dependency_sets[i],
                max_attempts=self._config.max_retries + 1,
            )
            for i, description in enumerate(descriptions)
        ]
        plan = ExecutionPlan(plan_id=uuid.uuid4().hex, request=request, tasks=tasks)
        self._recompute(plan)
        self._publish("planning.plan_created", plan)
        return plan

    def plan_from_cowork_response(self, response: CoworkTaskResponse) -> ExecutionPlan:
        """Wrap an already-planned CoworkTaskResponse (Phase 9/10) in a
        tracked ExecutionPlan — sequential by step order, same
        collaborator-assignment logic as create_plan().
        """
        tasks = [
            PlanTask(
                id=str(step.step_id),
                description=step.description,
                collaborator=select_role(step.description),
                depends_on=(str(response.steps[i - 1].step_id),) if i > 0 else (),
                max_attempts=self._config.max_retries + 1,
            )
            for i, step in enumerate(response.steps)
        ]
        plan = ExecutionPlan(plan_id=response.task_id, request=response.summary, tasks=tasks)
        self._recompute(plan)
        self._publish("planning.plan_created", plan)
        return plan

    # -- scheduling / parallel work ---------------------------------------

    def parallel_groups(self, plan: ExecutionPlan) -> list[list[str]]:
        """Task ids grouped into waves — every task within one wave can
        run in parallel with the rest of that wave.
        """
        return topological_waves(plan.tasks)

    def next_ready_tasks(self, plan: ExecutionPlan) -> list[PlanTask]:
        self._recompute(plan)
        return [t for t in plan.tasks if t.status == TaskStatus.READY]

    # -- progress tracking -------------------------------------------------

    def mark_in_progress(self, plan: ExecutionPlan, task_id: str) -> None:
        task = plan.get_task(task_id)
        task.status = TaskStatus.IN_PROGRESS
        task.attempts += 1
        self._publish("planning.task_started", plan, task)

    def mark_done(self, plan: ExecutionPlan, task_id: str, result: object = None) -> None:
        task = plan.get_task(task_id)
        task.status = TaskStatus.DONE
        task.result = result
        task.error = None
        self._recompute(plan)
        self._publish("planning.task_completed", plan, task)

    def mark_failed(self, plan: ExecutionPlan, task_id: str, error: str) -> None:
        task = plan.get_task(task_id)
        task.status = TaskStatus.FAILED
        task.error = error
        self._recompute(plan)
        self._publish("planning.task_failed", plan, task)

    def retry_failed(self, plan: ExecutionPlan, task_id: str) -> bool:
        """Reset a failed task to PENDING if it has attempts remaining.
        Returns whether a retry was actually scheduled.

        Also reopens every SKIPPED task in the plan back to PENDING —
        SKIPPED exists only because *some* dependency FAILED, and
        retrying may resolve that, so anything downstream deserves
        another chance to become READY rather than staying stuck.
        _recompute() re-skips whatever still has another failed/skipped
        dependency, so this is safe even in a plan with multiple
        independent failures.
        """
        task = plan.get_task(task_id)
        if task.status != TaskStatus.FAILED or task.attempts >= task.max_attempts:
            return False
        task.status = TaskStatus.PENDING
        task.error = None
        for other in plan.tasks:
            if other.status == TaskStatus.SKIPPED:
                other.status = TaskStatus.PENDING
                other.error = None
        self._recompute(plan)
        self._publish("planning.task_retrying", plan, task)
        return True

    # -- display -------------------------------------------------------------

    def should_preview(self, plan: ExecutionPlan) -> bool:
        """"Display the plan before execution when appropriate": true
        for a large plan, or one touching a risky collaborator/keyword.
        """
        if len(plan.tasks) > self._config.preview_task_threshold:
            return True
        risky_collaborators = set(self._config.preview_risky_collaborators)
        for task in plan.tasks:
            if task.collaborator.value in risky_collaborators:
                return True
            lowered = task.description.lower()
            if any(keyword in lowered for keyword in self._config.preview_risky_keywords):
                return True
        return False

    def render_plan(self, plan: ExecutionPlan) -> str:
        lines = [f"Execution Plan: {plan.request}", f"({len(plan.tasks)} task(s))", ""]
        try:
            waves = self.parallel_groups(plan)
        except Exception as exc:  # CyclicDependencyError — still render, flag it
            lines.append(f"WARNING: {exc}")
            waves = [[task.id for task in plan.tasks]]
        for wave_index, wave in enumerate(waves):
            lines.append(f"Wave {wave_index + 1}:")
            for task_id in wave:
                task = plan.get_task(task_id)
                depends_on = ", ".join(task.depends_on) or "none"
                lines.append(
                    f"  [{task.status.value}] {task.id}: {task.description} "
                    f"(collaborator={task.collaborator.value}, depends_on={depends_on})"
                )
        return "\n".join(lines)

    # -- internals -----------------------------------------------------------

    def _recompute(self, plan: ExecutionPlan) -> None:
        """Advance PENDING tasks to READY (all dependencies DONE) or
        SKIPPED (a dependency FAILED/SKIPPED) — repeated until stable,
        since one SKIPPED task can cascade to its own dependents.
        """
        by_id = {t.id: t for t in plan.tasks}
        changed = True
        while changed:
            changed = False
            for task in plan.tasks:
                if task.status != TaskStatus.PENDING:
                    continue
                deps = [by_id[d] for d in task.depends_on if d in by_id]
                if any(d.status in (TaskStatus.FAILED, TaskStatus.SKIPPED) for d in deps):
                    task.status = TaskStatus.SKIPPED
                    task.error = "a dependency failed"
                    changed = True
                elif all(d.status == TaskStatus.DONE for d in deps):
                    task.status = TaskStatus.READY
                    changed = True

    def _publish(self, name: str, plan: ExecutionPlan, task: PlanTask | None = None) -> None:
        if self._events is None:
            return
        payload = {"plan_id": plan.plan_id, "request": plan.request}
        if task is not None:
            payload.update({"task_id": task.id, "status": task.status.value})
        self._events.publish(name, payload, source="planning_engine")
