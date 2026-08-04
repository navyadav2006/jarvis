"""WorkflowRunner: "background jobs" — a small bounded worker-thread
pool that calls `WorkflowEngine.run_workflow()` off a `queue.Queue`, so
`submit()` returns immediately instead of blocking the caller for the
whole run. Same "small state, one thread-safe primitive" shape as
`core/speech/queue.py`'s `SpeechQueue`, using the stdlib `queue.Queue`
directly since it's already thread-safe — no extra lock needed here.

Not a second execution path: every run still goes through
`WorkflowEngine.run_workflow()`, so a workflow triggered in the
background is identical to one run synchronously, and both stay
subject to whatever `WorkflowActionPort` enforces (Phase 19's
SecurityManager, in production).
"""

from __future__ import annotations

import logging
import queue
import threading

from jarvis.core.workflow.engine import WorkflowEngine
from jarvis.core.workflow.types import WorkflowTrigger

logger = logging.getLogger(__name__)

_STOP = object()


class WorkflowRunner:
    def __init__(self, engine: WorkflowEngine, *, max_workers: int = 2) -> None:
        self._engine = engine
        self._max_workers = max_workers
        self._queue: queue.Queue = queue.Queue()
        self._workers: list[threading.Thread] = []

    def start(self) -> None:
        if self._workers:
            return
        for i in range(self._max_workers):
            worker = threading.Thread(
                target=self._worker_loop, name=f"jarvis-workflow-worker-{i}", daemon=True
            )
            worker.start()
            self._workers.append(worker)
        logger.info("Started WorkflowRunner with %d worker(s)", self._max_workers)

    def stop(self) -> None:
        if not self._workers:
            return
        for _ in self._workers:
            self._queue.put(_STOP)
        for worker in self._workers:
            worker.join(timeout=5)
        self._workers = []
        logger.info("Stopped WorkflowRunner")

    def submit(
        self, workflow_id: str, *, trigger: WorkflowTrigger = WorkflowTrigger.MANUAL
    ) -> None:
        self._queue.put((workflow_id, trigger))

    def _worker_loop(self) -> None:
        while True:
            item = self._queue.get()
            if item is _STOP:
                return
            workflow_id, trigger = item
            try:
                self._engine.run_workflow(workflow_id, trigger=trigger)
            except Exception:
                logger.exception("Unhandled error running workflow %s", workflow_id)
