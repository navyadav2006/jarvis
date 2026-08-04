from __future__ import annotations

import pytest

from jarvis.core.exceptions import WorkflowNotFoundError
from jarvis.core.workflow.types import Workflow, WorkflowStep


def test_get_step_returns_matching_step() -> None:
    step = WorkflowStep(id="a", name="A", action="filesystem.read")
    workflow = Workflow(id="w1", name="wf", steps=[step])
    assert workflow.get_step("a") is step


def test_get_step_raises_for_unknown_id() -> None:
    workflow = Workflow(id="w1", name="wf", steps=[])
    with pytest.raises(WorkflowNotFoundError):
        workflow.get_step("missing")
