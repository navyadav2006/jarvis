from __future__ import annotations

from pathlib import Path

from jarvis.core.workflow.engine import WorkflowEngine
from jarvis.core.workflow.ports import WorkflowActionResult
from jarvis.core.workflow.runner import WorkflowRunner
from jarvis.core.workflow.scheduler import WorkflowScheduler
from jarvis.core.workflow.store import SqliteWorkflowStore
from jarvis.core.workflow.types import WorkflowSchedule, WorkflowStep, WorkflowTrigger


class FakeActionPort:
    def execute(self, action: str, parameters: dict) -> WorkflowActionResult:
        return WorkflowActionResult(success=True, output="ok")


class SpyRunner:
    def __init__(self) -> None:
        self.submitted: list[tuple[str, WorkflowTrigger]] = []

    def submit(
        self, workflow_id: str, *, trigger: WorkflowTrigger = WorkflowTrigger.MANUAL
    ) -> None:
        self.submitted.append((workflow_id, trigger))


def _engine(tmp_path: Path) -> WorkflowEngine:
    store = SqliteWorkflowStore(tmp_path / "wf.db")
    return WorkflowEngine(store, FakeActionPort())


def test_first_tick_primes_without_submitting(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    engine.create_workflow(
        "demo",
        [WorkflowStep(id="a", name="A", action="x.y")],
        schedule=WorkflowSchedule(interval_seconds=60),
    )
    runner = SpyRunner()
    scheduler = WorkflowScheduler(engine, runner)  # type: ignore[arg-type]
    scheduler.tick()
    assert runner.submitted == []


def test_due_workflow_is_submitted_with_scheduled_trigger(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    workflow = engine.create_workflow(
        "demo",
        [WorkflowStep(id="a", name="A", action="x.y")],
        schedule=WorkflowSchedule(interval_seconds=60),
    )
    runner = SpyRunner()
    scheduler = WorkflowScheduler(engine, runner)  # type: ignore[arg-type]
    scheduler.tick()  # prime
    scheduler._next_run_at[workflow.id] = scheduler._next_run_at[workflow.id].replace(year=2000)
    scheduler.tick()  # now overdue
    assert runner.submitted == [(workflow.id, WorkflowTrigger.SCHEDULED)]


def test_disabled_workflow_is_never_submitted(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    engine.create_workflow(
        "demo",
        [WorkflowStep(id="a", name="A", action="x.y")],
        schedule=WorkflowSchedule(interval_seconds=60),
        enabled=False,
    )
    runner = SpyRunner()
    scheduler = WorkflowScheduler(engine, runner)  # type: ignore[arg-type]
    scheduler.tick()
    scheduler.tick()
    assert runner.submitted == []


def test_unscheduled_workflow_is_never_submitted(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    engine.create_workflow("demo", [WorkflowStep(id="a", name="A", action="x.y")])
    runner = SpyRunner()
    scheduler = WorkflowScheduler(engine, runner)  # type: ignore[arg-type]
    scheduler.tick()
    scheduler.tick()
    assert runner.submitted == []


def test_editing_schedule_takes_effect_next_tick(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    workflow = engine.create_workflow(
        "demo",
        [WorkflowStep(id="a", name="A", action="x.y")],
        schedule=WorkflowSchedule(interval_seconds=60),
    )
    runner = SpyRunner()
    scheduler = WorkflowScheduler(engine, runner)  # type: ignore[arg-type]
    scheduler.tick()
    engine.update_workflow(workflow.id, enabled=False)
    scheduler.tick()
    assert workflow.id not in scheduler._next_run_at


def test_start_and_stop_manage_the_background_thread(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    runner = WorkflowRunner(engine, max_workers=1)
    runner.start()
    scheduler = WorkflowScheduler(engine, runner, poll_interval_seconds=1000)
    scheduler.start()
    assert scheduler._thread is not None
    scheduler.stop()
    assert scheduler._thread is None
    runner.stop()
