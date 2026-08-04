"""workflow.yaml — the Autonomous Workflow engine's settings (Phase 20):
where its SQLite store lives, how often the scheduler polls for due
workflows, and how many runs can execute concurrently.

No `enabled` flag: WorkflowEngine/WorkflowRunner/WorkflowScheduler are
always constructed and always running, the same "always real, no Null
default" choice Phase 17's `PlanningEngine` and Phase 19's
`SecurityManager` made — an empty workflow store with an idle scheduler
is harmless, and "autonomous workflows" has no meaningful disabled
state the way an optional network backend (Cowork, vault) does.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

WORKFLOW_FILENAME = "workflow.yaml"


class WorkflowConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    database_path: Path = Path("data/workflows.db")

    # How often WorkflowScheduler checks whether any scheduled workflow
    # is due — same polling shape as ConfigManager's live-reload watcher.
    scheduler_poll_interval_seconds: float = Field(30.0, gt=0)

    # WorkflowRunner's background worker pool size — how many workflow
    # runs can execute at once.
    max_concurrent_runs: int = Field(2, gt=0)
