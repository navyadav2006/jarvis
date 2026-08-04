"""Evaluates an explicit `WorkflowCondition` against a run's step
results so far — "implement conditional execution". Pure function, no
I/O, deliberately not an `eval()`-style expression language: the
closed set of `ConditionType`s is the whole surface, so a workflow
(including one Cowork generated) can never smuggle arbitrary code into
a condition.

The *implicit* default rule ("run iff every dependency succeeded",
used when a step's `condition` is None) lives in `engine.py`, not here
— this module only evaluates conditions that were explicitly set.
"""

from __future__ import annotations

from jarvis.core.workflow.types import (
    ConditionType,
    WorkflowCondition,
    WorkflowStepResult,
    WorkflowStepStatus,
)


def evaluate_condition(
    condition: WorkflowCondition, results: dict[str, WorkflowStepResult]
) -> bool:
    if condition.type == ConditionType.ALWAYS:
        return True

    if condition.step_id is None or condition.step_id not in results:
        return False  # malformed/dangling reference — fail closed, don't run
    result = results[condition.step_id]

    if condition.type == ConditionType.ON_SUCCESS:
        return result.status == WorkflowStepStatus.SUCCEEDED
    if condition.type == ConditionType.ON_FAILURE:
        return result.status == WorkflowStepStatus.FAILED
    if condition.type == ConditionType.OUTPUT_EQUALS:
        return result.output == condition.value
    if condition.type == ConditionType.OUTPUT_CONTAINS:
        try:
            return condition.value in result.output  # type: ignore[operator]
        except TypeError:
            return False
    return False
