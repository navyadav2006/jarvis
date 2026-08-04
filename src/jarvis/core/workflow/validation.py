"""Upfront validation for a `Workflow`'s steps and schedule, run once at
create/update time rather than discovered mid-run — the same
"fail fast at the edge, not deep inside execution" preference
`core/config/`'s startup validation and Phase 15's permission checks
share.
"""

from __future__ import annotations

from jarvis.core.exceptions import (
    InvalidWorkflowConditionError,
    InvalidWorkflowScheduleError,
    WorkflowError,
)
from jarvis.core.workflow.cron import CronSchedule
from jarvis.core.workflow.dependencies import topological_waves
from jarvis.core.workflow.types import ConditionType, WorkflowSchedule, WorkflowStep


def validate_steps(steps: list[WorkflowStep]) -> None:
    ids = [step.id for step in steps]
    if len(ids) != len(set(ids)):
        raise WorkflowError(f"duplicate step ids: {sorted({i for i in ids if ids.count(i) > 1})}")

    known = set(ids)
    for step in steps:
        unknown = [dep for dep in step.depends_on if dep not in known]
        if unknown:
            raise WorkflowError(f"step {step.id!r} depends_on unknown step id(s): {unknown}")

        condition = step.condition
        if condition is not None and condition.type != ConditionType.ALWAYS:
            if condition.step_id is None or condition.step_id not in step.depends_on:
                raise InvalidWorkflowConditionError(
                    f"step {step.id!r}'s condition references {condition.step_id!r}, "
                    "which must be listed in its own depends_on"
                )

    # Raises CyclicWorkflowError for a non-DAG; also proves every step
    # has a valid execution order before the workflow is ever run.
    topological_waves(steps)


def validate_schedule(schedule: WorkflowSchedule | None) -> None:
    if schedule is None:
        return
    both_or_neither = (schedule.interval_seconds is not None) == (schedule.cron is not None)
    if both_or_neither:
        raise InvalidWorkflowScheduleError(
            "WorkflowSchedule needs exactly one of interval_seconds or cron set"
        )
    if schedule.interval_seconds is not None and schedule.interval_seconds <= 0:
        raise InvalidWorkflowScheduleError("interval_seconds must be positive")
    if schedule.cron is not None:
        CronSchedule.parse(schedule.cron)  # raises InvalidCronExpressionError if malformed
