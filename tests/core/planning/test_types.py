from __future__ import annotations

import pytest

from jarvis.core.cowork.collaborators import CollaboratorRole
from jarvis.core.exceptions import UnknownTaskError
from jarvis.core.planning.types import ExecutionPlan, PlanTask, TaskStatus


def test_get_task_raises_for_unknown_id() -> None:
    plan = ExecutionPlan(plan_id="p1", request="x", tasks=[])
    with pytest.raises(UnknownTaskError):
        plan.get_task("missing")


def test_is_complete_false_when_a_task_is_pending() -> None:
    task = PlanTask(id="0", description="x", collaborator=CollaboratorRole.PLANNER)
    plan = ExecutionPlan(plan_id="p1", request="x", tasks=[task])
    assert plan.is_complete is False


def test_is_complete_true_when_all_done_or_skipped() -> None:
    done = PlanTask(
        id="0", description="x", collaborator=CollaboratorRole.PLANNER, status=TaskStatus.DONE
    )
    skipped = PlanTask(
        id="1", description="y", collaborator=CollaboratorRole.PLANNER, status=TaskStatus.SKIPPED
    )
    plan = ExecutionPlan(plan_id="p1", request="x", tasks=[done, skipped])
    assert plan.is_complete is True
