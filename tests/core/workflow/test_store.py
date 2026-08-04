from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from jarvis.core.workflow.store import SqliteWorkflowStore
from jarvis.core.workflow.types import (
    ConditionType,
    Workflow,
    WorkflowCondition,
    WorkflowRun,
    WorkflowSchedule,
    WorkflowStatus,
    WorkflowStep,
    WorkflowStepResult,
    WorkflowStepStatus,
    WorkflowTrigger,
)


def _workflow(**overrides) -> Workflow:
    defaults = dict(
        id="w1",
        name="test workflow",
        description="a workflow",
        steps=[
            WorkflowStep(
                id="a",
                name="A",
                action="filesystem.read",
                parameters={"path": "x"},
                condition=WorkflowCondition(type=ConditionType.ALWAYS),
            ),
            WorkflowStep(id="b", name="B", action="filesystem.write", depends_on=("a",)),
        ],
        schedule=WorkflowSchedule(interval_seconds=60),
    )
    defaults.update(overrides)
    return Workflow(**defaults)


def test_save_and_get_workflow_round_trips(tmp_path: Path) -> None:
    store = SqliteWorkflowStore(tmp_path / "wf.db")
    workflow = _workflow()
    store.save_workflow(workflow)

    loaded = store.get_workflow(workflow.id)
    assert loaded is not None
    assert loaded.name == "test workflow"
    assert len(loaded.steps) == 2
    assert loaded.steps[0].condition == WorkflowCondition(type=ConditionType.ALWAYS)
    assert loaded.steps[1].depends_on == ("a",)
    assert loaded.schedule == WorkflowSchedule(interval_seconds=60)


def test_get_missing_workflow_returns_none(tmp_path: Path) -> None:
    store = SqliteWorkflowStore(tmp_path / "wf.db")
    assert store.get_workflow("nope") is None


def test_save_workflow_upserts(tmp_path: Path) -> None:
    store = SqliteWorkflowStore(tmp_path / "wf.db")
    workflow = _workflow()
    store.save_workflow(workflow)
    workflow.name = "renamed"
    store.save_workflow(workflow)

    loaded = store.get_workflow(workflow.id)
    assert loaded is not None
    assert loaded.name == "renamed"
    assert len(store.list_workflows()) == 1


def test_list_workflows_returns_all(tmp_path: Path) -> None:
    store = SqliteWorkflowStore(tmp_path / "wf.db")
    store.save_workflow(_workflow(id="w1"))
    store.save_workflow(_workflow(id="w2"))
    assert {w.id for w in store.list_workflows()} == {"w1", "w2"}


def test_delete_workflow(tmp_path: Path) -> None:
    store = SqliteWorkflowStore(tmp_path / "wf.db")
    store.save_workflow(_workflow())
    assert store.delete_workflow("w1") is True
    assert store.get_workflow("w1") is None
    assert store.delete_workflow("w1") is False


def _run(**overrides) -> WorkflowRun:
    defaults = dict(
        id="r1",
        workflow_id="w1",
        trigger=WorkflowTrigger.MANUAL,
        status=WorkflowStatus.SUCCEEDED,
        step_results={
            "a": WorkflowStepResult(
                step_id="a",
                status=WorkflowStepStatus.SUCCEEDED,
                output="ok",
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
            )
        },
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
    )
    defaults.update(overrides)
    return WorkflowRun(**defaults)


def test_save_and_get_run_round_trips(tmp_path: Path) -> None:
    store = SqliteWorkflowStore(tmp_path / "wf.db")
    run = _run()
    store.save_run(run)

    loaded = store.get_run(run.id)
    assert loaded is not None
    assert loaded.status == WorkflowStatus.SUCCEEDED
    assert loaded.step_results["a"].output == "ok"


def test_list_runs_filters_by_workflow_and_orders_newest_first(tmp_path: Path) -> None:
    store = SqliteWorkflowStore(tmp_path / "wf.db")
    older = _run(id="r1", started_at=datetime(2026, 1, 1, tzinfo=UTC))
    newer = _run(id="r2", started_at=datetime(2026, 1, 2, tzinfo=UTC))
    other_workflow = _run(id="r3", workflow_id="w2", started_at=datetime(2026, 1, 3, tzinfo=UTC))
    store.save_run(older)
    store.save_run(newer)
    store.save_run(other_workflow)

    runs = store.list_runs(workflow_id="w1")
    assert [r.id for r in runs] == ["r2", "r1"]


def test_list_runs_respects_limit(tmp_path: Path) -> None:
    store = SqliteWorkflowStore(tmp_path / "wf.db")
    for i in range(5):
        store.save_run(_run(id=f"r{i}", started_at=datetime(2026, 1, i + 1, tzinfo=UTC)))
    assert len(store.list_runs(limit=2)) == 2
