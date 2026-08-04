"""SecurityAuditTrail: "audit logs" — one JSON line per security
decision SecurityManager ever makes, allowed or denied. Same JSON
Lines shape and append-only reasoning as
`core/execution/audit.py`'s `AuditTrail` (Phase 15) — kept as a
separate, small class rather than importing that one, since the two
audit trails log structurally different entries
(`SecurityAuditEntry` vs. `execution.types.AuditEntry`) and this
module must not depend on core/execution/ (SecurityManager is meant to
sit in front of it, not the other way around).
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict
from pathlib import Path

from jarvis.core.security.types import SecurityAuditEntry


class SecurityAuditTrail:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()

    def record(self, entry: SecurityAuditEntry) -> None:
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
