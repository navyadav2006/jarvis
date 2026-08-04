"""WorkflowScheduler: "scheduled workflows" and "recurring maintenance"
— a polling background thread (same mtime-poll shape as
`core/config/manager.py`'s live-reload watcher) that submits a
workflow to `WorkflowRunner` when its schedule says it's due, then
recomputes the next due time.

"Recurring maintenance" isn't a separate mechanism: it's just a
`Workflow` with a `schedule` set, like any other scheduled workflow —
there's nothing maintenance-specific to build here.

Re-reads `WorkflowEngine.list_workflows()` every tick rather than
caching workflow definitions at `start()` — so an edit made via
"workflow editing" (a schedule change, or disabling a workflow) takes
effect on the scheduler's very next tick, without a restart.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime, timedelta

from jarvis.core.workflow.cron import next_run_after
from jarvis.core.workflow.engine import WorkflowEngine
from jarvis.core.workflow.runner import WorkflowRunner
from jarvis.core.workflow.types import Workflow, WorkflowTrigger

logger = logging.getLogger(__name__)


class WorkflowScheduler:
    def __init__(
        self,
        engine: WorkflowEngine,
        runner: WorkflowRunner,
        *,
        poll_interval_seconds: float = 30.0,
    ) -> None:
        self._engine = engine
        self._runner = runner
        self._poll_interval = poll_interval_seconds
        self._next_run_at: dict[str, datetime] = {}
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, name="jarvis-workflow-scheduler", daemon=True
        )
        self._thread.start()
        logger.info(
            "Started WorkflowScheduler (poll_interval=%.1fs)", self._poll_interval
        )

    def stop(self) -> None:
        if self._thread is None:
            return
        self._stop_event.set()
        self._thread.join(timeout=5)
        self._thread = None
        logger.info("Stopped WorkflowScheduler")

    def _loop(self) -> None:
        while not self._stop_event.wait(self._poll_interval):
            try:
                self.tick()
            except Exception:
                logger.exception("Unexpected error in workflow scheduler loop")

    def tick(self) -> None:
        """Check every scheduled workflow and submit any that are due.
        Public (not just `_tick`) so a caller can drive it deterministically
        in tests instead of waiting on the poll interval.
        """
        now = datetime.now(UTC)
        live_ids = set()
        for workflow in self._engine.list_workflows():
            live_ids.add(workflow.id)
            if not workflow.enabled or workflow.schedule is None:
                self._next_run_at.pop(workflow.id, None)
                continue

            due_at = self._next_run_at.get(workflow.id)
            if due_at is None:
                self._next_run_at[workflow.id] = self._compute_next(workflow, now)
                continue

            if now >= due_at:
                self._runner.submit(workflow.id, trigger=WorkflowTrigger.SCHEDULED)
                self._next_run_at[workflow.id] = self._compute_next(workflow, now)

        for stale_id in set(self._next_run_at) - live_ids:
            del self._next_run_at[stale_id]

    def _compute_next(self, workflow: Workflow, after: datetime) -> datetime:
        schedule = workflow.schedule
        assert schedule is not None  # only called when schedule is set
        if schedule.interval_seconds is not None:
            return after + timedelta(seconds=schedule.interval_seconds)
        assert schedule.cron is not None
        return next_run_after(schedule.cron, after)
