"""SqliteWorkflowStore: a real WorkflowStorePort implementation backed
by the standard library's `sqlite3` — no new dependency, same choice
Phase 12's `SqliteMemoryManager` made. Each workflow/run is stored as
one row with its steps/schedule/step_results serialized to a JSON
column rather than normalized into further tables: nothing here needs
to query *inside* a step (e.g. "find all workflows with a filesystem
step"), so the simpler single-row-per-entity shape avoids speculative
schema design for queries this phase doesn't need.

A single `threading.Lock` guards every query — same reasoning as
`SqliteMemoryManager`: sqlite3 connections aren't safe to share across
threads without one, and this store is called from the API, the
background `WorkflowRunner` pool, and `WorkflowScheduler` concurrently.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

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

_SCHEMA = """
CREATE TABLE IF NOT EXISTS workflows (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    steps TEXT NOT NULL,
    schedule TEXT,
    enabled INTEGER NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS workflow_runs (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    trigger_kind TEXT NOT NULL,
    status TEXT NOT NULL,
    step_results TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    error TEXT
);
"""


def _condition_to_dict(condition: WorkflowCondition | None) -> dict | None:
    if condition is None:
        return None
    return {"type": condition.type.value, "step_id": condition.step_id, "value": condition.value}


def _condition_from_dict(data: dict | None) -> WorkflowCondition | None:
    if data is None:
        return None
    return WorkflowCondition(
        type=ConditionType(data["type"]), step_id=data["step_id"], value=data["value"]
    )


def _step_to_dict(step: WorkflowStep) -> dict:
    return {
        "id": step.id,
        "name": step.name,
        "action": step.action,
        "parameters": step.parameters,
        "depends_on": list(step.depends_on),
        "condition": _condition_to_dict(step.condition),
    }


def _step_from_dict(data: dict) -> WorkflowStep:
    return WorkflowStep(
        id=data["id"],
        name=data["name"],
        action=data["action"],
        parameters=data["parameters"],
        depends_on=tuple(data["depends_on"]),
        condition=_condition_from_dict(data["condition"]),
    )


def _schedule_to_dict(schedule: WorkflowSchedule | None) -> dict | None:
    if schedule is None:
        return None
    return {"interval_seconds": schedule.interval_seconds, "cron": schedule.cron}


def _schedule_from_dict(data: dict | None) -> WorkflowSchedule | None:
    if data is None:
        return None
    return WorkflowSchedule(interval_seconds=data["interval_seconds"], cron=data["cron"])


def _step_result_to_dict(result: WorkflowStepResult) -> dict:
    return {
        "step_id": result.step_id,
        "status": result.status.value,
        "output": result.output,
        "error": result.error,
        "started_at": result.started_at.isoformat() if result.started_at else None,
        "finished_at": result.finished_at.isoformat() if result.finished_at else None,
    }


def _step_result_from_dict(data: dict) -> WorkflowStepResult:
    return WorkflowStepResult(
        step_id=data["step_id"],
        status=WorkflowStepStatus(data["status"]),
        output=data["output"],
        error=data["error"],
        started_at=datetime.fromisoformat(data["started_at"]) if data["started_at"] else None,
        finished_at=datetime.fromisoformat(data["finished_at"]) if data["finished_at"] else None,
    )


def _row_to_workflow(row: sqlite3.Row) -> Workflow:
    steps = [_step_from_dict(d) for d in json.loads(row["steps"])]
    schedule = _schedule_from_dict(json.loads(row["schedule"]) if row["schedule"] else None)
    return Workflow(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        steps=steps,
        schedule=schedule,
        enabled=bool(row["enabled"]),
        created_by=row["created_by"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _row_to_run(row: sqlite3.Row) -> WorkflowRun:
    step_results = {
        step_id: _step_result_from_dict(d) for step_id, d in json.loads(row["step_results"]).items()
    }
    return WorkflowRun(
        id=row["id"],
        workflow_id=row["workflow_id"],
        trigger=WorkflowTrigger(row["trigger_kind"]),
        status=WorkflowStatus(row["status"]),
        step_results=step_results,
        started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
        finished_at=datetime.fromisoformat(row["finished_at"]) if row["finished_at"] else None,
        error=row["error"],
    )


class SqliteWorkflowStore:
    """Implements core.workflow.ports.WorkflowStorePort."""

    def __init__(self, database_path: Path) -> None:
        self._lock = threading.Lock()
        db_path = Path(database_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    # -- workflows -----------------------------------------------------------

    def save_workflow(self, workflow: Workflow) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO workflows "
                "(id, name, description, steps, schedule, enabled, created_by, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "name=excluded.name, description=excluded.description, "
                "steps=excluded.steps, schedule=excluded.schedule, "
                "enabled=excluded.enabled, updated_at=excluded.updated_at",
                (
                    workflow.id,
                    workflow.name,
                    workflow.description,
                    json.dumps([_step_to_dict(s) for s in workflow.steps]),
                    json.dumps(_schedule_to_dict(workflow.schedule)),
                    int(workflow.enabled),
                    workflow.created_by,
                    workflow.created_at.isoformat(),
                    workflow.updated_at.isoformat(),
                ),
            )
            self._conn.commit()

    def get_workflow(self, workflow_id: str) -> Workflow | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM workflows WHERE id = ?", (workflow_id,)
            ).fetchone()
        return _row_to_workflow(row) if row is not None else None

    def list_workflows(self) -> list[Workflow]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM workflows ORDER BY created_at ASC").fetchall()
        return [_row_to_workflow(row) for row in rows]

    def delete_workflow(self, workflow_id: str) -> bool:
        with self._lock:
            cursor = self._conn.execute("DELETE FROM workflows WHERE id = ?", (workflow_id,))
            self._conn.commit()
            return cursor.rowcount > 0

    # -- runs ("workflow history") --------------------------------------------

    def save_run(self, run: WorkflowRun) -> None:
        step_results_json = json.dumps(
            {sid: _step_result_to_dict(r) for sid, r in run.step_results.items()}
        )
        with self._lock:
            self._conn.execute(
                "INSERT INTO workflow_runs "
                "(id, workflow_id, trigger_kind, status, step_results, started_at, "
                "finished_at, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "status=excluded.status, step_results=excluded.step_results, "
                "started_at=excluded.started_at, finished_at=excluded.finished_at, "
                "error=excluded.error",
                (
                    run.id,
                    run.workflow_id,
                    run.trigger.value,
                    run.status.value,
                    step_results_json,
                    run.started_at.isoformat() if run.started_at else None,
                    run.finished_at.isoformat() if run.finished_at else None,
                    run.error,
                ),
            )
            self._conn.commit()

    def get_run(self, run_id: str) -> WorkflowRun | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM workflow_runs WHERE id = ?", (run_id,)
            ).fetchone()
        return _row_to_run(row) if row is not None else None

    def list_runs(self, *, workflow_id: str | None = None, limit: int = 50) -> list[WorkflowRun]:
        with self._lock:
            if workflow_id is not None:
                rows = self._conn.execute(
                    "SELECT * FROM workflow_runs WHERE workflow_id = ? "
                    "ORDER BY started_at DESC LIMIT ?",
                    (workflow_id, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM workflow_runs ORDER BY started_at DESC LIMIT ?", (limit,)
                ).fetchall()
        return [_row_to_run(row) for row in rows]

    def close(self) -> None:
        with self._lock:
            self._conn.close()
