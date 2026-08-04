"""SqliteMemoryManager: a real MemoryManagerPort implementation backed
by the standard library's `sqlite3` — no new dependency, and no
embeddings (per this phase's explicit scope), just durable storage plus
the importance/recency/keyword ranking in ranking.py.

`summarize_session()` is a deterministic, heuristic summary (the
session's most recent remembered turns, joined and truncated) — not an
LLM-generated one. A real summarizer belongs to whichever future phase
wires this up to Cowork's Memory Manager collaborator
(core/cowork/collaborators.py); this phase's job is giving Jarvis a
working, structured memory API to call, not language generation.

A single `threading.Lock` guards every query: sqlite3 connections
aren't safe to share across threads without one, and this store is
expected to be called from multiple threads (the API, a future voice
pipeline, etc.) the same way LocalFilesystemService (Phase 4) is.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

from jarvis.core.config.memory_config import LongTermMemoryConfig
from jarvis.core.memory.ranking import rank_records
from jarvis.core.memory.types import ConversationTurn, MemoryQuery, MemoryRecord

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    kind TEXT NOT NULL,
    session_id TEXT,
    importance REAL NOT NULL,
    created_at TEXT NOT NULL,
    last_accessed_at TEXT,
    temporary INTEGER NOT NULL,
    tags TEXT NOT NULL
);
"""


def _row_to_record(row: sqlite3.Row) -> MemoryRecord:
    return MemoryRecord(
        id=row["id"],
        content=row["content"],
        kind=row["kind"],
        session_id=row["session_id"],
        importance=row["importance"],
        created_at=datetime.fromisoformat(row["created_at"]),
        last_accessed_at=(
            datetime.fromisoformat(row["last_accessed_at"]) if row["last_accessed_at"] else None
        ),
        temporary=bool(row["temporary"]),
        tags=tuple(json.loads(row["tags"])),
    )


class SqliteMemoryManager:
    """Implements core.memory.ports.MemoryManagerPort."""

    def __init__(self, config: LongTermMemoryConfig) -> None:
        self._config = config
        self._lock = threading.Lock()
        db_path = Path(config.database_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute(_SCHEMA)
            self._conn.commit()

    def remember_turn(self, session_id: str, turn: ConversationTurn) -> MemoryRecord:
        content = f"User: {turn.request_text}\nAssistant: {turn.response_text}"
        return self._insert(
            content=content,
            kind="turn",
            session_id=session_id,
            importance=0.3,
            created_at=turn.timestamp,
            temporary=True,
            tags=(),
        )

    def store_knowledge(
        self,
        content: str,
        *,
        session_id: str | None = None,
        importance: float = 0.6,
        tags: tuple[str, ...] = (),
        temporary: bool = False,
    ) -> MemoryRecord:
        return self._insert(
            content=content,
            kind="fact",
            session_id=session_id,
            importance=importance,
            created_at=datetime.now(UTC),
            temporary=temporary,
            tags=tags,
        )

    def recall(self, query: MemoryQuery) -> list[MemoryRecord]:
        clauses = []
        params: list[object] = []
        if query.session_id is not None:
            clauses.append("session_id = ?")
            params.append(query.session_id)
        if query.kinds:
            placeholders = ",".join("?" for _ in query.kinds)
            clauses.append(f"kind IN ({placeholders})")
            params.extend(query.kinds)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        with self._lock:
            rows = self._conn.execute(
                f"SELECT * FROM memory_records {where}", params
            ).fetchall()
        records = [_row_to_record(row) for row in rows]
        ranked = rank_records(records, query.text)[: query.limit]

        if ranked:
            self._touch([r.id for r in ranked if r.id is not None])
        return ranked

    def get_by_ids(self, record_ids: list[int]) -> list[MemoryRecord]:
        if not record_ids:
            return []
        placeholders = ",".join("?" for _ in record_ids)
        with self._lock:
            rows = self._conn.execute(
                f"SELECT * FROM memory_records WHERE id IN ({placeholders})", record_ids
            ).fetchall()
        return [_row_to_record(row) for row in rows]

    def summarize_session(self, session_id: str) -> str:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM memory_records WHERE session_id = ? AND kind = 'turn' "
                "ORDER BY created_at ASC",
                (session_id,),
            ).fetchall()
        turns = [_row_to_record(row) for row in rows]
        if not turns:
            summary = f"No remembered turns for session {session_id!r} yet."
        else:
            lines = [t.content.splitlines()[0][:120] for t in turns[-5:]]
            summary = f"Session {session_id!r} ({len(turns)} turn(s)): " + " | ".join(lines)

        self._insert(
            content=summary,
            kind="summary",
            session_id=session_id,
            importance=0.5,
            created_at=datetime.now(UTC),
            temporary=False,
            tags=(),
        )
        return summary

    def forget(self, *, session_id: str | None = None, temporary_only: bool = True) -> int:
        clauses = []
        params: list[object] = []
        if temporary_only:
            clauses.append("temporary = 1")
        if session_id is not None:
            clauses.append("session_id = ?")
            params.append(session_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        with self._lock:
            cursor = self._conn.execute(f"DELETE FROM memory_records {where}", params)
            self._conn.commit()
            return cursor.rowcount

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -- internals ---------------------------------------------------------

    def _insert(
        self,
        *,
        content: str,
        kind: str,
        session_id: str | None,
        importance: float,
        created_at: datetime,
        temporary: bool,
        tags: tuple[str, ...],
    ) -> MemoryRecord:
        with self._lock:
            cursor = self._conn.execute(
                "INSERT INTO memory_records "
                "(content, kind, session_id, importance, created_at, last_accessed_at, "
                "temporary, tags) VALUES (?, ?, ?, ?, ?, NULL, ?, ?)",
                (
                    content,
                    kind,
                    session_id,
                    importance,
                    created_at.isoformat(),
                    int(temporary),
                    json.dumps(list(tags)),
                ),
            )
            self._conn.commit()
            record_id = cursor.lastrowid
        return MemoryRecord(
            id=record_id,
            content=content,
            kind=kind,  # type: ignore[arg-type]
            session_id=session_id,
            importance=importance,
            created_at=created_at,
            last_accessed_at=None,
            temporary=temporary,
            tags=tags,
        )

    def _touch(self, record_ids: list[int]) -> None:
        now = datetime.now(UTC).isoformat()
        with self._lock:
            self._conn.executemany(
                "UPDATE memory_records SET last_accessed_at = ? WHERE id = ?",
                [(now, record_id) for record_id in record_ids],
            )
            self._conn.commit()
