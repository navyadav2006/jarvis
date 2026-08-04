"""RateLimiter: a sliding-window request counter, keyed per
`(requested_by, level)` — so a burst of DANGEROUS actions from one
requester can't be masked by, or block, a separate requester's or a
different level's normal traffic.

In-memory only (a `collections.deque` of timestamps per key, pruned on
each check) — no persistence needed, since a rate limit is inherently
about "recent" activity, not history. Thread-safe via a single lock,
the same "small state, one lock" shape `SpeechQueue`/`SqliteMemoryManager`
use.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from jarvis.core.security.types import PermissionLevel

_WINDOW_SECONDS = 60.0


class RateLimiter:
    def __init__(self, limits: dict[PermissionLevel, int]) -> None:
        self._limits = limits
        self._lock = threading.Lock()
        self._events: dict[tuple[str, PermissionLevel], deque[float]] = defaultdict(deque)

    def allow(self, requested_by: str, level: PermissionLevel) -> bool:
        """Record this attempt and return whether it's within the
        limit. Every call — allowed or not — counts against the
        window, so a denied burst doesn't get to retry unthrottled.
        """
        limit = self._limits.get(level)
        if limit is None:
            return True  # no configured limit for this level

        now = time.monotonic()
        key = (requested_by, level)
        with self._lock:
            timestamps = self._events[key]
            self._prune(timestamps, now)
            timestamps.append(now)
            return len(timestamps) <= limit

    def remaining(self, requested_by: str, level: PermissionLevel) -> int | None:
        limit = self._limits.get(level)
        if limit is None:
            return None
        now = time.monotonic()
        with self._lock:
            timestamps = self._events[(requested_by, level)]
            self._prune(timestamps, now)
            return max(0, limit - len(timestamps))

    @staticmethod
    def _prune(timestamps: deque[float], now: float) -> None:
        while timestamps and now - timestamps[0] > _WINDOW_SECONDS:
            timestamps.popleft()
