"""Plain data types for the Autonomous Workflow engine (Phase 20).

Own types, independent of core/planning/'s `PlanTask`/`ExecutionPlan` —
same "own types per module" rule every module since core/memory/ has
followed. `WorkflowEngine` doesn't replace `PlanningEngine`: a
`Workflow` is a *persisted, reusable, schedulable* definition (saved to
`WorkflowStorePort`, run zero or more times, possibly on a recurring
schedule); an `ExecutionPlan` is a one-shot, in-memory tracker for a
single request's decomposition. They solve adjacent but different
problems and don't need to share types to coexist.

`WorkflowStep` is a frozen *definition* — what to run, its
dependencies, and (optionally) an explicit condition. `WorkflowStepResult`
is the mutable *outcome* of running one step during one `WorkflowRun` —
kept separate so a `Workflow` can be run many times without its
definition being mutated by any particular run, the same
definition/outcome split `core/execution/`'s `ExecutionRequest`/
`ExecutionResult` already uses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from jarvis.core.exceptions import WorkflowNotFoundError


class WorkflowStepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"  # its condition evaluated false, or a dependency failed


class WorkflowStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class WorkflowTrigger(StrEnum):
    MANUAL = "manual"
    SCHEDULED = "scheduled"
    COWORK = "cowork"


class ConditionType(StrEnum):
    ALWAYS = "always"  # run regardless of any dependency's outcome
    ON_SUCCESS = "on_success"  # the referenced step succeeded
    ON_FAILURE = "on_failure"  # the referenced step failed
    OUTPUT_EQUALS = "output_equals"  # the referenced step's output == value
    OUTPUT_CONTAINS = "output_contains"  # value in the referenced step's output


@dataclass(frozen=True)
class WorkflowCondition:
    """"Conditional execution": an explicit override of the default
    "run only if every dependency succeeded" rule. `step_id` must be
    one of the owning `WorkflowStep.depends_on` for every type except
    ALWAYS (validated at workflow-creation time, `validation.py`) — the
    engine executes steps wave-by-wave in dependency order, so a
    condition can only safely inspect a step that's guaranteed to have
    already finished.
    """

    type: ConditionType
    step_id: str | None = None
    value: object = None


@dataclass(frozen=True)
class WorkflowStep:
    id: str
    name: str
    action: str  # dotted "category.action", e.g. "filesystem.delete"
    parameters: dict = field(default_factory=dict)
    depends_on: tuple[str, ...] = ()
    # None means the default rule: run iff every dependency SUCCEEDED.
    condition: WorkflowCondition | None = None


@dataclass(frozen=True)
class WorkflowSchedule:
    """Exactly one of the two must be set — validated in
    `validation.py`, not here, so the dataclass itself stays a plain
    value object like every other frozen config-adjacent type.
    """

    interval_seconds: int | None = None
    cron: str | None = None


@dataclass
class Workflow:
    """A saved, reusable, optionally-scheduled multi-step definition.
    Mutable (unlike most of core/'s frozen value objects) — the same
    "stateful by necessity" reasoning `core/planning/types.py`'s
    `ExecutionPlan` documents, since `enabled`/`updated_at` change after
    creation without the workflow becoming a new entity.
    """

    id: str
    name: str
    steps: list[WorkflowStep] = field(default_factory=list)
    description: str = ""
    schedule: WorkflowSchedule | None = None
    enabled: bool = True
    created_by: str = "user"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def get_step(self, step_id: str) -> WorkflowStep:
        for step in self.steps:
            if step.id == step_id:
                return step
        raise WorkflowNotFoundError(f"no step {step_id!r} in workflow {self.id!r}")


@dataclass
class WorkflowStepResult:
    step_id: str
    status: WorkflowStepStatus = WorkflowStepStatus.PENDING
    output: object = None
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


@dataclass
class WorkflowRun:
    """One execution ("workflow history" entry) of a `Workflow`."""

    id: str
    workflow_id: str
    trigger: WorkflowTrigger = WorkflowTrigger.MANUAL
    status: WorkflowStatus = WorkflowStatus.PENDING
    step_results: dict[str, WorkflowStepResult] = field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
