"""In-memory session/state management.

Session state is process-local and ephemeral by design (see
models.Session's docstring for how this differs from MemoryPort).
A `threading.Lock` protects the session dict itself (creation/lookup)
against concurrent FastAPI requests; mutation of a single Session's
fields is not separately locked, on the assumption that one session_id
represents one active conversation handled by one request at a time —
concurrent turns on the *same* session_id racing each other is a
known, accepted limitation for Phase 2, not something this store
silently hides.
"""

from __future__ import annotations

import logging
import threading

from jarvis.orchestrator.models import Session

logger = logging.getLogger(__name__)


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def get_or_create(self, session_id: str) -> Session:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                session = Session(session_id=session_id)
                self._sessions[session_id] = session
                logger.debug("Created new session %r", session_id)
            return session

    def get(self, session_id: str) -> Session | None:
        with self._lock:
            return self._sessions.get(session_id)

    def clear(self, session_id: str) -> None:
        with self._lock:
            removed = self._sessions.pop(session_id, None)
        if removed is not None:
            logger.debug("Cleared session %r", session_id)

    def session_ids(self) -> list[str]:
        with self._lock:
            return list(self._sessions.keys())
