"""decompose_request(): "break large requests into tasks" — a
deterministic, dependency-free text splitter, not an LLM call. Same
scope choice as core/memory/store.py's summarize_session() and
core/vault/backlinks.py: a real, useful default that a future phase
could replace with a Cowork-backed (Planner collaborator) decomposition
without changing anything downstream, since both produce the same
`list[str]` shape `PlanningEngine.create_plan()` consumes.
"""

from __future__ import annotations

import re

# Numbered/bulleted list markers ("1.", "2)", "- ", "* ") and explicit
# sequencing words are the two splitting signals; a request with
# neither is treated as a single task.
_LIST_MARKER_RE = re.compile(r"(?:^|\n)\s*(?:\d+[.)]|[-*])\s+")
_SEQUENCE_SPLIT_RE = re.compile(r"\s*(?:;|\bthen\b|\band then\b)\s*", re.IGNORECASE)


def decompose_request(request: str) -> list[str]:
    request = request.strip()
    if not request:
        return []

    if _LIST_MARKER_RE.search(request):
        parts = [p.strip() for p in _LIST_MARKER_RE.split(request) if p.strip()]
        if parts:
            return parts

    parts = [p.strip() for p in _SEQUENCE_SPLIT_RE.split(request) if p.strip()]
    return parts if len(parts) > 1 else [request]
