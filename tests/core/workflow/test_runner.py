from __future__ import annotations

import time
from pathlib import Path

from jarvis.core.workflow.engine import WorkflowEngine
from jarvis.core.workflow.ports import WorkflowActionResult
from jarvis.core.workflow.runner import WorkflowRunner
from jarvis.core.workflow.store import SqliteWorkflowStore
from jarvis.core.workflow.types import WorkflowStatus, WorkflowStep, WorkflowTrigger


class FakeActionPort:
    def execute(self, action: str, parameters: dict) -> WorkflowActionResult:
        return WorkflowActionResult(success=True, output="ok")


def _wait_for(predicate, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_submit_runs_the_workflow_in_the_background(tmp_path: Path) -> None:
    store = SqliteWorkflowStore(tmp_path / "wf.db")
    engine = WorkflowEngine(store, FakeActionPort())
    workflow = engine.create_workflow("demo", [WorkflowStep(id="a", name="A", action="x.y")])

    runner = WorkflowRunner(engine, max_workers=1)
    runner.start()
    try:
        runner.submit(workflow.id, trigger=WorkflowTrigger.SCHEDULED)
        assert _wait_for(lambda: len(engine.list_runs(workflow.id)) == 1)
        run = engine.list_runs(workflow.id)[0]
        assert run.status == WorkflowStatus.SUCCEEDED
        assert run.trigger == WorkflowTrigger.SCHEDULED
    finally:
        runner.stop()


def test_a_workflow_error_does_not_kill_the_worker(tmp_path: Path) -> None:
    store = SqliteWorkflowStore(tmp_path / "wf.db")
    engine = WorkflowEngine(store, FakeActionPort())
    workflow = engine.create_workflow("demo", [WorkflowStep(id="a", name="A", action="x.y")])

    runner = WorkflowRunner(engine, max_workers=1)
    runner.start()
    try:
        runner.submit("does-not-exist")  # raises WorkflowNotFoundError inside the worker
        runner.submit(workflow.id)  # worker must still process this one
        assert _wait_for(lambda: len(engine.list_runs(workflow.id)) == 1)
    finally:
        runner.stop()


def test_stop_is_idempotent_and_joins_workers(tmp_path: Path) -> None:
    store = SqliteWorkflowStore(tmp_path / "wf.db")
    engine = WorkflowEngine(store, FakeActionPort())
    runner = WorkflowRunner(engine, max_workers=2)
    runner.start()
    runner.stop()
    runner.stop()  # must not raise
