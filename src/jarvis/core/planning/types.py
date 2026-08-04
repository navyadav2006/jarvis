"""Plain data types for the Planning Engine.

`PlanTask`/`ExecutionPlan` are deliberately mutable (unlike the frozen
value objects most of `core/` uses) — a plan's whole point is tracking
state that changes over time (status, attempts, results) as tasks run,
the same "stateful by necessity" shape orchestrator/models.py's
`Session` uses for the same reason.

`collaborator` reuses Phase 10's `CollaboratorRole` rather than
reinventing an assignment concept — "assign collaborators" means
exactly the eight roles Cowork already knows how to reason as.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from jarvis.core.cowork.collaborators import CollaboratorRole
from jarvis.core.exceptions import UnknownTaskError


class TaskStatus(StrEnum):
    PENDING = "pending"  # not yet ready — still waiting on a dependency
    READY = "ready"  # dependencies satisfied, not yet started
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"  # a dependency failed permanently; this can never run


@dataclass
class PlanTask:
    id: str
    description: str
    collaborator: CollaboratorRole
    depends_on: tuple[str, ...] = ()
    status: TaskStatus = TaskStatus.PENDING
    attempts: int = 0
    max_attempts: int = 3
    error: str | None = None
    result: object = None


@dataclass
class ExecutionPlan:
    """A tracked, ordered set of tasks for one request — "generate
    execution plans" produces one of these; everything else in
    engine.py operates on it.
    """

    plan_id: str
    request: str
    tasks: list[PlanTask] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def get_task(self, task_id: str) -> PlanTask:
        for task in self.tasks:
            if task.id == task_id:
                return task
        raise UnknownTaskError(f"no task {task_id!r} in plan {self.plan_id!r}")

    @property
    def is_complete(self) -> bool:
        return all(t.status in (TaskStatus.DONE, TaskStatus.SKIPPED) for t in self.tasks)

    @property
    def has_failed_tasks(self) -> bool:
        return any(t.status == TaskStatus.FAILED for t in self.tasks)
