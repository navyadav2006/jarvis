from __future__ import annotations

import pytest

from jarvis.core.exceptions import (
    CyclicWorkflowError,
    InvalidCronExpressionError,
    InvalidWorkflowConditionError,
    InvalidWorkflowScheduleError,
    WorkflowError,
)
from jarvis.core.workflow.types import (
    ConditionType,
    WorkflowCondition,
    WorkflowSchedule,
    WorkflowStep,
)
from jarvis.core.workflow.validation import validate_schedule, validate_steps


def test_valid_steps_pass() -> None:
    validate_steps(
        [
            WorkflowStep(id="a", name="A", action="x.y"),
            WorkflowStep(id="b", name="B", action="x.y", depends_on=("a",)),
        ]
    )


def test_duplicate_ids_rejected() -> None:
    with pytest.raises(WorkflowError):
        validate_steps(
            [
                WorkflowStep(id="a", name="A", action="x.y"),
                WorkflowStep(id="a", name="A2", action="x.y"),
            ]
        )


def test_unknown_dependency_rejected() -> None:
    with pytest.raises(WorkflowError):
        validate_steps([WorkflowStep(id="a", name="A", action="x.y", depends_on=("ghost",))])


def test_cyclic_steps_rejected() -> None:
    with pytest.raises(CyclicWorkflowError):
        validate_steps(
            [
                WorkflowStep(id="a", name="A", action="x.y", depends_on=("b",)),
                WorkflowStep(id="b", name="B", action="x.y", depends_on=("a",)),
            ]
        )


def test_condition_referencing_a_real_dependency_passes() -> None:
    validate_steps(
        [
            WorkflowStep(id="a", name="A", action="x.y"),
            WorkflowStep(
                id="b",
                name="B",
                action="x.y",
                depends_on=("a",),
                condition=WorkflowCondition(type=ConditionType.ON_FAILURE, step_id="a"),
            ),
        ]
    )


def test_condition_referencing_a_non_dependency_rejected() -> None:
    with pytest.raises(InvalidWorkflowConditionError):
        validate_steps(
            [
                WorkflowStep(id="a", name="A", action="x.y"),
                WorkflowStep(
                    id="b",
                    name="B",
                    action="x.y",
                    condition=WorkflowCondition(type=ConditionType.ON_SUCCESS, step_id="a"),
                ),
            ]
        )


def test_always_condition_does_not_require_a_step_id() -> None:
    validate_steps(
        [
            WorkflowStep(
                id="a",
                name="A",
                action="x.y",
                condition=WorkflowCondition(type=ConditionType.ALWAYS),
            )
        ]
    )


def test_none_schedule_is_fine() -> None:
    validate_schedule(None)


def test_interval_only_is_fine() -> None:
    validate_schedule(WorkflowSchedule(interval_seconds=60))


def test_cron_only_is_fine() -> None:
    validate_schedule(WorkflowSchedule(cron="0 2 * * *"))


def test_both_set_is_rejected() -> None:
    with pytest.raises(InvalidWorkflowScheduleError):
        validate_schedule(WorkflowSchedule(interval_seconds=60, cron="0 2 * * *"))


def test_neither_set_is_rejected() -> None:
    with pytest.raises(InvalidWorkflowScheduleError):
        validate_schedule(WorkflowSchedule())


def test_negative_interval_rejected() -> None:
    with pytest.raises(InvalidWorkflowScheduleError):
        validate_schedule(WorkflowSchedule(interval_seconds=-1))


def test_malformed_cron_rejected() -> None:
    with pytest.raises(InvalidCronExpressionError):
        validate_schedule(WorkflowSchedule(cron="not a cron"))
