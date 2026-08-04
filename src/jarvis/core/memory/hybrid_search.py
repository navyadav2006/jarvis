"""HybridMemorySearch: keyword + semantic search over long-term memory,
producing ranked, cited results — the "give Cowork only the relevant
memories instead of the entire vault" piece (Phase 14).

Combines two independently-ranked candidate lists:

  - MemoryManagerPort.recall() (Phase 12): importance + keyword-overlap
    + recency (ranking.py), no vectors involved.
  - EmbeddingIndexPort.search() (this phase): cosine similarity over
    HashingEmbeddingProvider vectors.

A record found by both gets a combined score (weighted by
`SemanticMemoryConfig.semantic_weight`); a record found by only one
source keeps that source's own (weighted) score. This is deliberately
simple rank fusion, not a learned re-ranker — appropriate for a single
vault, and easy to replace once a real embedding model
(EmbeddingProvider) makes the semantic half of this worth more.

`relevant_memories()` returns plain JSON-safe dicts, not MemoryCitation
objects — that's what lets it satisfy core/cowork/ports.py's
CoworkContextProvider Protocol structurally, without core/cowork/
importing anything from core/memory/ (see workspace.py's docstring for
why that direction matters).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from jarvis.core.memory.embeddings import EmbeddingProvider
from jarvis.core.memory.ports import EmbeddingIndexPort, MemoryManagerPort
from jarvis.core.memory.types import MemoryQuery, MemoryRecord


@dataclass(frozen=True)
class MemoryCitation:
    """One ranked, citable memory result."""

    record: MemoryRecord
    score: float
    matched_via: str  # "keyword", "semantic", or "both"

    @property
    def citation(self) -> str:
        """A short, human-readable reference to where this memory came
        from — a vault note path if the record was vault-indexed
        (tagged "vault:<path>" by VaultIndexer), otherwise its kind and
        id.
        """
        vault_tag = next((t for t in self.record.tags if t.startswith("vault:")), None)
        if vault_tag:
            return vault_tag.removeprefix("vault:")
        return f"{self.record.kind}#{self.record.id}"


class HybridMemorySearch:
    def __init__(
        self,
        *,
        memory: MemoryManagerPort,
        semantic_index: EmbeddingIndexPort,
        provider: EmbeddingProvider,
        semantic_weight: float = 0.4,
    ) -> None:
        self._memory = memory
        self._semantic_index = semantic_index
        self._provider = provider
        self._semantic_weight = semantic_weight

    def search(
        self, query_text: str, *, session_id: str | None = None, limit: int = 5
    ) -> list[MemoryCitation]:
        keyword_records = self._memory.recall(
            MemoryQuery(text=query_text, session_id=session_id, limit=max(limit * 2, limit))
        )
        # recall() already sorted these by the full importance/keyword/
        # recency blend (ranking.py); `importance` is used here as a
        # single-number stand-in for "how strongly recall() ranked it,"
        # not literally just the stored importance field's own meaning.
        keyword_scores = {r.id: r.importance for r in keyword_records if r.id is not None}
        by_id = {r.id: r for r in keyword_records if r.id is not None}

        query_vector = self._semantic_index.embed(query_text)
        semantic_hits = self._semantic_index.search(query_vector, limit=max(limit * 2, limit))
        semantic_scores = dict(semantic_hits)

        # A semantic-only hit's record may not be in the keyword
        # candidate set at all — fetch those directly rather than
        # dropping them, or "hybrid" search would quietly degrade to
        # "keyword search with a semantic tiebreaker."
        missing_ids = [rid for rid in semantic_scores if rid not in by_id]
        for record in self._memory.get_by_ids(missing_ids):
            if record.id is not None:
                by_id[record.id] = record

        keyword_weight = 1.0 - self._semantic_weight
        all_ids = set(keyword_scores) | set(semantic_scores)
        citations: list[MemoryCitation] = []
        for record_id in all_ids:
            record = by_id.get(record_id)
            if record is None:
                continue
            has_keyword = record_id in keyword_scores
            has_semantic = record_id in semantic_scores
            score = keyword_weight * keyword_scores.get(
                record_id, 0.0
            ) + self._semantic_weight * semantic_scores.get(record_id, 0.0)
            matched_via = "both" if has_keyword and has_semantic else (
                "keyword" if has_keyword else "semantic"
            )
            citations.append(MemoryCitation(record=record, score=score, matched_via=matched_via))

        citations.sort(key=lambda c: c.score, reverse=True)
        return citations[:limit]

    def relevant_memories(self, instruction: str, *, limit: int = 5) -> list[dict[str, Any]]:
        return [
            {
                "content": citation.record.content,
                "citation": citation.citation,
                "score": round(citation.score, 4),
                "matched_via": citation.matched_via,
            }
            for citation in self.search(instruction, limit=limit)
        ]
