from __future__ import annotations

from jarvis.core.workflow.conditions import evaluate_condition
from jarvis.core.workflow.types import (
    ConditionType,
    WorkflowCondition,
    WorkflowStepResult,
    WorkflowStepStatus,
)


def _results(**statuses: WorkflowStepStatus) -> dict[str, WorkflowStepResult]:
    return {sid: WorkflowStepResult(step_id=sid, status=status) for sid, status in statuses.items()}


def test_always_is_always_true() -> None:
    condition = WorkflowCondition(type=ConditionType.ALWAYS)
    assert evaluate_condition(condition, {}) is True


def test_on_success_true_when_referenced_step_succeeded() -> None:
    condition = WorkflowCondition(type=ConditionType.ON_SUCCESS, step_id="a")
    results = _results(a=WorkflowStepStatus.SUCCEEDED)
    assert evaluate_condition(condition, results) is True


def test_on_success_false_when_referenced_step_failed() -> None:
    condition = WorkflowCondition(type=ConditionType.ON_SUCCESS, step_id="a")
    results = _results(a=WorkflowStepStatus.FAILED)
    assert evaluate_condition(condition, results) is False


def test_on_failure_true_when_referenced_step_failed() -> None:
    condition = WorkflowCondition(type=ConditionType.ON_FAILURE, step_id="a")
    results = _results(a=WorkflowStepStatus.FAILED)
    assert evaluate_condition(condition, results) is True


def test_output_equals() -> None:
    condition = WorkflowCondition(type=ConditionType.OUTPUT_EQUALS, step_id="a", value=42)
    results = {"a": WorkflowStepResult(step_id="a", status=WorkflowStepStatus.SUCCEEDED, output=42)}
    assert evaluate_condition(condition, results) is True
    results["a"].output = 43
    assert evaluate_condition(condition, results) is False


def test_output_contains() -> None:
    condition = WorkflowCondition(type=ConditionType.OUTPUT_CONTAINS, step_id="a", value="err")
    results = {
        "a": WorkflowStepResult(
            step_id="a", status=WorkflowStepStatus.SUCCEEDED, output="an error occurred"
        )
    }
    assert evaluate_condition(condition, results) is True


def test_output_contains_handles_non_containable_output_gracefully() -> None:
    condition = WorkflowCondition(type=ConditionType.OUTPUT_CONTAINS, step_id="a", value="x")
    results = {"a": WorkflowStepResult(step_id="a", status=WorkflowStepStatus.SUCCEEDED, output=42)}
    assert evaluate_condition(condition, results) is False


def test_dangling_step_id_reference_fails_closed() -> None:
    condition = WorkflowCondition(type=ConditionType.ON_SUCCESS, step_id="nonexistent")
    assert evaluate_condition(condition, {}) is False


def test_missing_step_id_for_non_always_fails_closed() -> None:
    condition = WorkflowCondition(type=ConditionType.ON_SUCCESS, step_id=None)
    assert evaluate_condition(condition, {}) is False
