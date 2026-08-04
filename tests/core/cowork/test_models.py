from __future__ import annotations

import pytest
from pydantic import ValidationError

from jarvis.core.cowork.models import (
    AutomationActionModel,
    CoworkPlanStep,
    CoworkTaskRequest,
    CoworkTaskResponse,
)


def test_task_request_generates_a_task_id_when_not_given() -> None:
    request = CoworkTaskRequest(session_id="s1", instruction="do it")
    assert request.task_id  # non-empty


def test_task_request_round_trips_through_json() -> None:
    request = CoworkTaskRequest(session_id="s1", instruction="do it", context={"k": "v"})
    restored = CoworkTaskRequest.model_validate(request.model_dump(mode="json"))
    assert restored == request


def test_task_response_requires_task_id_and_summary() -> None:
    with pytest.raises(ValidationError):
        CoworkTaskResponse.model_validate({"steps": []})


def test_plan_step_rejects_unknown_action_type() -> None:
    with pytest.raises(ValidationError):
        CoworkPlanStep.model_validate(
            {"step_id": 1, "description": "x", "action_type": "delete_c_drive"}
        )


def test_task_request_is_frozen() -> None:
    request = CoworkTaskRequest(session_id="s1", instruction="do it")
    with pytest.raises(ValidationError):
        request.instruction = "something else"  # type: ignore[misc]


def test_automation_action_model_has_no_execute_method() -> None:
    # Structural proof of the "Cowork's output is inert data" boundary:
    # nothing on this model can perform the action it describes.
    action = AutomationActionModel(name="click", parameters={"x": 1})
    assert not hasattr(action, "execute")
    assert not hasattr(action, "run")
