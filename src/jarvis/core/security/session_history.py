"""SessionHistory: "session history" — a bounded, in-memory log of
security decisions per `requested_by` identity, kept separate from
`SecurityAuditTrail` (which is durable and unbounded on disk).

Keyed by `requested_by` (e.g. "cowork", a plugin name), not a
conversation `session_id`: nothing in the `AutomationAction`/
`ExecutionRequest` chain (Phase 9/15) threads a chat session id down
to this layer today, and "who is asking" is what a security review
actually needs to answer ("what has this requester been doing"), which
`requested_by` already captures. A future phase wiring a real
conversation session_id through is a natural extension, not a
redesign, of this class.
"""

from __future__ import annotations

import threading
from collections import defaultdict, deque

from jarvis.core.security.types import SecurityDecision


class SessionHistory:
    def __init__(self, limit: int = 200) -> None:
        self._limit = limit
        self._lock = threading.Lock()
        self._history: dict[str, deque[SecurityDecision]] = defaultdict(
            lambda: deque(maxlen=limit)
        )

    def record(self, requested_by: str, decision: SecurityDecision) -> None:
        with self._lock:
            self._history[requested_by].append(decision)

    def for_requester(self, requested_by: str) -> list[SecurityDecision]:
        with self._lock:
            return list(self._history.get(requested_by, ()))

    def clear(self, requested_by: str) -> None:
        with self._lock:
            self._history.pop(requested_by, None)
