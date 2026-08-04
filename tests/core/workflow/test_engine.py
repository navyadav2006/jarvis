from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core.cowork.models import AutomationActionModel, CoworkPlanStep, CoworkTaskResponse
from jarvis.core.events import EventBus
from jarvis.core.exceptions import WorkflowNotFoundError
from jarvis.core.workflow.engine import WorkflowEngine
from jarvis.core.workflow.ports import WorkflowActionResult
from jarvis.core.workflow.store import SqliteWorkflowStore
from jarvis.core.workflow.types import (
    ConditionType,
    WorkflowCondition,
    WorkflowStatus,
    WorkflowStep,
    WorkflowStepStatus,
    WorkflowTrigger,
)


class FakeActionPort:
    def __init__(self, *, fail_actions: set[str] | None = None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self._fail_actions = fail_actions or set()

    def execute(self, action: str, parameters: dict) -> WorkflowActionResult:
        self.calls.append((action, parameters))
        if action in self._fail_actions:
            return WorkflowActionResult(success=False, error=f"{action} failed")
        return WorkflowActionResult(success=True, output=f"ok:{action}")


def _engine(tmp_path: Path, *, fail_actions: set[str] | None = None, events=None):
    store = SqliteWorkflowStore(tmp_path / "wf.db")
    port = FakeActionPort(fail_actions=fail_actions)
    return WorkflowEngine(store, port, events=events), port


# -- CRUD ("workflow editing") ---------------------------------------------


def test_create_and_get_workflow(tmp_path: Path) -> None:
    engine, _ = _engine(tmp_path)
    workflow = engine.create_workflow("demo", [WorkflowStep(id="a", name="A", action="x.y")])
    assert engine.get_workflow(workflow.id).name == "demo"


def test_get_unknown_workflow_raises(tmp_path: Path) -> None:
    engine, _ = _engine(tmp_path)
    with pytest.raises(WorkflowNotFoundError):
        engine.get_workflow("nope")


def test_update_workflow_changes_fields(tmp_path: Path) -> None:
    engine, _ = _engine(tmp_path)
    workflow = engine.create_workflow("demo", [WorkflowStep(id="a", name="A", action="x.y")])
    updated = engine.update_workflow(workflow.id, name="renamed", enabled=False)
    assert updated.name == "renamed"
    assert updated.enabled is False


def test_update_workflow_leaves_unspecified_fields_unchanged(tmp_path: Path) -> None:
    engine, _ = _engine(tmp_path)
    workflow = engine.create_workflow(
        "demo", [WorkflowStep(id="a", name="A", action="x.y")], description="original"
    )
    updated = engine.update_workflow(workflow.id, name="renamed")
    assert updated.description == "original"


def test_delete_workflow(tmp_path: Path) -> None:
    engine, _ = _engine(tmp_path)
    workflow = engine.create_workflow("demo", [WorkflowStep(id="a", name="A", action="x.y")])
    engine.delete_workflow(workflow.id)
    with pytest.raises(WorkflowNotFoundError):
        engine.get_workflow(workflow.id)


def test_delete_unknown_workflow_raises(tmp_path: Path) -> None:
    engine, _ = _engine(tmp_path)
    with pytest.raises(WorkflowNotFoundError):
        engine.delete_workflow("nope")


def test_list_workflows(tmp_path: Path) -> None:
    engine, _ = _engine(tmp_path)
    engine.create_workflow("a", [WorkflowStep(id="a", name="A", action="x.y")])
    engine.create_workflow("b", [WorkflowStep(id="a", name="A", action="x.y")])
    assert len(engine.list_workflows()) == 2


# -- execution ("multi-step automation") -----------------------------------


def test_run_workflow_executes_steps_in_order(tmp_path: Path) -> None:
    engine, port = _engine(tmp_path)
    workflow = engine.create_workflow(
        "demo",
        [
            WorkflowStep(id="a", name="A", action="filesystem.read"),
            WorkflowStep(id="b", name="B", action="filesystem.write", depends_on=("a",)),
        ],
    )
    run = engine.run_workflow(workflow.id)
    assert run.status == WorkflowStatus.SUCCEEDED
    assert [c[0] for c in port.calls] == ["filesystem.read", "filesystem.write"]


def test_default_condition_skips_dependent_on_upstream_failure(tmp_path: Path) -> None:
    engine, port = _engine(tmp_path, fail_actions={"terminal.run"})
    workflow = engine.create_workflow(
        "demo",
        [
            WorkflowStep(id="a", name="A", action="terminal.run"),
            WorkflowStep(id="b", name="B", action="filesystem.write", depends_on=("a",)),
        ],
    )
    run = engine.run_workflow(workflow.id)
    assert run.status == WorkflowStatus.FAILED
    assert run.step_results["a"].status == WorkflowStepStatus.FAILED
    assert run.step_results["b"].status == WorkflowStepStatus.SKIPPED
    assert [c[0] for c in port.calls] == ["terminal.run"]  # b never actually ran


def test_always_condition_runs_despite_upstream_failure(tmp_path: Path) -> None:
    engine, port = _engine(tmp_path, fail_actions={"terminal.run"})
    workflow = engine.create_workflow(
        "demo",
        [
            WorkflowStep(id="a", name="A", action="terminal.run"),
            WorkflowStep(
                id="cleanup",
                name="cleanup",
                action="filesystem.delete",
                depends_on=("a",),
                condition=WorkflowCondition(type=ConditionType.ALWAYS),
            ),
        ],
    )
    run = engine.run_workflow(workflow.id)
    assert run.step_results["cleanup"].status == WorkflowStepStatus.SUCCEEDED
    assert "filesystem.delete" in [c[0] for c in port.calls]


def test_on_failure_condition_acts_as_error_handler(tmp_path: Path) -> None:
    engine, _ = _engine(tmp_path, fail_actions={"terminal.run"})
    workflow = engine.create_workflow(
        "demo",
        [
            WorkflowStep(id="a", name="A", action="terminal.run"),
            WorkflowStep(
                id="handler",
                name="handler",
                action="filesystem.write",
                depends_on=("a",),
                condition=WorkflowCondition(type=ConditionType.ON_FAILURE, step_id="a"),
            ),
        ],
    )
    run = engine.run_workflow(workflow.id)
    assert run.step_results["handler"].status == WorkflowStepStatus.SUCCEEDED


def test_unhandled_exception_from_action_port_marks_step_failed(tmp_path: Path) -> None:
    store = SqliteWorkflowStore(tmp_path / "wf.db")

    class ExplodingPort:
        def execute(self, action: str, parameters: dict) -> WorkflowActionResult:
            raise RuntimeError("boom")

    engine = WorkflowEngine(store, ExplodingPort())
    workflow = engine.create_workflow("demo", [WorkflowStep(id="a", name="A", action="x.y")])
    run = engine.run_workflow(workflow.id)
    assert run.status == WorkflowStatus.FAILED
    assert "boom" in run.step_results["a"].error


def test_run_is_recorded_in_history(tmp_path: Path) -> None:
    engine, _ = _engine(tmp_path)
    workflow = engine.create_workflow("demo", [WorkflowStep(id="a", name="A", action="x.y")])
    engine.run_workflow(workflow.id)
    engine.run_workflow(workflow.id)
    assert len(engine.list_runs(workflow.id)) == 2


def test_run_trigger_is_recorded(tmp_path: Path) -> None:
    engine, _ = _engine(tmp_path)
    workflow = engine.create_workflow("demo", [WorkflowStep(id="a", name="A", action="x.y")])
    run = engine.run_workflow(workflow.id, trigger=WorkflowTrigger.SCHEDULED)
    assert run.trigger == WorkflowTrigger.SCHEDULED


def test_events_published_for_run_and_step_lifecycle(tmp_path: Path) -> None:
    events = EventBus()
    received: list[str] = []
    names = (
        "workflow.run_started",
        "workflow.step_started",
        "workflow.step_finished",
        "workflow.run_finished",
    )
    for name in names:
        events.subscribe(name, lambda e, name=name: received.append(name))
    engine, _ = _engine(tmp_path, events=events)
    workflow = engine.create_workflow("demo", [WorkflowStep(id="a", name="A", action="x.y")])
    engine.run_workflow(workflow.id)
    assert received == [
        "workflow.run_started",
        "workflow.step_started",
        "workflow.step_finished",
        "workflow.run_finished",
    ]


# -- Cowork bridge -----------------------------------------------------------


def test_workflow_from_cowork_response_keeps_only_automation_steps(tmp_path: Path) -> None:
    engine, _ = _engine(tmp_path)
    response = CoworkTaskResponse(
        task_id="t1",
        summary="organize downloads",
        steps=[
            CoworkPlanStep(
                step_id=1,
                description="list files",
                action_type="automation",
                automation=AutomationActionModel(name="filesystem.search", parameters={}),
            ),
            CoworkPlanStep(
                step_id=2, description="say done", action_type="respond", response_text="done"
            ),
            CoworkPlanStep(
                step_id=3,
                description="move files",
                action_type="automation",
                automation=AutomationActionModel(name="filesystem.move", parameters={}),
            ),
        ],
    )
    workflow = engine.workflow_from_cowork_response(response)
    assert [s.id for s in workflow.steps] == ["1", "3"]
    assert workflow.steps[1].depends_on == ("1",)  # sequential, skipping the dropped respond step
    assert workflow.created_by == "cowork"


# -- visualization -----------------------------------------------------------


def test_render_mermaid_includes_steps_and_edges(tmp_path: Path) -> None:
    engine, _ = _engine(tmp_path)
    workflow = engine.create_workflow(
        "demo",
        [
            WorkflowStep(id="a", name="Step A", action="x.y"),
            WorkflowStep(id="b", name="Step B", action="x.y", depends_on=("a",)),
        ],
    )
    mermaid = engine.render_mermaid(workflow.id)
    assert "flowchart TD" in mermaid
    assert "a --> b" in mermaid
    assert "Step A" in mermaid
