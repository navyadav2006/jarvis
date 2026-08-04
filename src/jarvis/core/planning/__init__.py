"""The Planning Engine (Phase 17): reusable task decomposition,
dependency estimation, parallel-work detection, collaborator
assignment, progress tracking, and retry — for every future feature
that needs to break a request into a trackable, multi-step plan, not
just Cowork requests.

`PlanningEngine` never executes anything itself; it produces and
tracks `ExecutionPlan`s. See `engine.py`'s module docstring for the
full design and docs/architecture.md's Phase 17 section for the
rationale.
"""

from __future__ import annotations

from jarvis.core.planning.decomposition import decompose_request
from jarvis.core.planning.dependencies import estimate_sequential_dependencies, topological_waves
from jarvis.core.planning.engine import PlanningEngine
from jarvis.core.planning.types import ExecutionPlan, PlanTask, TaskStatus

__all__ = [
    "ExecutionPlan",
    "PlanTask",
    "PlanningEngine",
    "TaskStatus",
    "decompose_request",
    "estimate_sequential_dependencies",
    "topological_waves",
]
