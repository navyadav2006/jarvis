"""VaultIndexer: indexes an Obsidian vault (Phase 13) into long-term
memory (Phase 12) plus the semantic index (this phase) — "index the
entire vault" and "incremental updates."

Incremental: a small JSON state file (content-hash per note path) is
the only thing consulted to decide whether a note needs re-indexing.
Re-running `index_vault()` on an unchanged vault does no SQLite writes
and no embedding computation at all — every note is skipped after one
cheap hash comparison. This is the same "content-addressed, cache
everything unnecessary work" idea `SemanticIndex`'s embedding cache
uses, applied one level up.

Each indexed note becomes one durable 'fact' MemoryRecord (tagged with
its vault path so results can cite it), plus one vector in
`SemanticIndex` keyed by that record's id — the two stay in lockstep by
construction, since index_note() is the only place either is written.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from jarvis.core.memory.ports import EmbeddingIndexPort, MemoryManagerPort
from jarvis.core.vault.ports import VaultPort

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IndexReport:
    indexed: int
    skipped: int
    failed: int


class VaultIndexer:
    def __init__(
        self,
        *,
        vault: VaultPort,
        memory: MemoryManagerPort,
        semantic_index: EmbeddingIndexPort,
        state_path: Path,
    ) -> None:
        self._vault = vault
        self._memory = memory
        self._semantic_index = semantic_index
        self._state_path = Path(state_path)
        self._state = self._load_state()

    def index_vault(self) -> IndexReport:
        indexed = skipped = failed = 0
        for path in self._vault.list_notes():
            try:
                if self.index_note(path):
                    indexed += 1
                else:
                    skipped += 1
            except Exception:
                logger.exception("Failed to index vault note %r", path)
                failed += 1
        return IndexReport(indexed=indexed, skipped=skipped, failed=failed)

    def index_note(self, path: str) -> bool:
        """Index one note if its content changed since last indexed.
        Returns True if it was (re-)indexed, False if skipped as
        unchanged.
        """
        note = self._vault.read_note(path)
        content_hash = hashlib.sha256(note.body.encode("utf-8")).hexdigest()
        if self._state.get(path) == content_hash:
            return False

        # MemoryManagerPort has no update-in-place API (Phase 12 is
        # append-only by design), so a re-index of a changed note
        # stores a fresh record rather than mutating one — the old
        # record simply ranks lower over time via ranking.py's recency
        # term, the same way any other stale memory would.
        record = self._memory.store_knowledge(
            note.body, tags=(f"vault:{path}",), importance=0.6, temporary=False
        )

        vector = self._semantic_index.embed(note.body)
        if record.id is not None:
            self._semantic_index.index(record.id, vector)

        self._state[path] = content_hash
        self._save_state()
        return True

    # -- internals -----------------------------------------------------------

    def _load_state(self) -> dict[str, str]:
        if not self._state_path.exists():
            return {}
        try:
            return json.loads(self._state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("Could not read %s; reindexing from scratch", self._state_path)
            return {}

    def _save_state(self) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(json.dumps(self._state), encoding="utf-8")
