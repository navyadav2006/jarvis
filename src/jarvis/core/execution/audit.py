"""AuditTrail: the durable execution audit trail (Phase 15) — one JSON
line per action ExecutionEngine ever handles, appended to
`execution.yaml`'s `audit_log_path`.

JSON Lines (not a JSON array) so appending never requires reading and
rewriting the whole file, and a crash mid-write corrupts at most the
last line, not the entire log — the same reasoning most real audit/log
formats use. Stdlib `json` only, no new dependency.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict
from pathlib import Path

from jarvis.core.execution.types import AuditEntry


class AuditTrail:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()

    def record(self, entry: AuditEntry) -> None:
        row = asdict(entry)
        row["timestamp"] = entry.timestamp.isoformat()
        line = json.dumps(row)
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")

    def read_all(self) -> list[dict]:
        if not self._path.exists():
            return []
        with self._path.open(encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
