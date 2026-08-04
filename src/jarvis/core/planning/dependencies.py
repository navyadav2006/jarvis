"""Dependency estimation and parallel-work detection — pure graph
algorithms over `PlanTask.depends_on`, no I/O, fully deterministic.

`estimate_sequential_dependencies()` is the default, heuristic answer
to "estimate dependencies" when a caller hands the planner plain task
descriptions with no explicit dependency information: each task depends
on the one before it, UNLESS its own text signals independence (a
handful of marker words — "meanwhile", "separately", "in parallel",
"also"). This is a deliberately simple heuristic, the same category of
choice Phase 12's importance/recency ranking and Phase 13's backlink
extraction made — good enough to be useful, honestly documented as not
true natural-language understanding.

`topological_waves()` is the real, general algorithm underneath
"detect parallel work": standard Kahn's-algorithm level-by-level
topological sort. It doesn't care how the dependency edges got there
(the heuristic above, or a caller-supplied explicit DAG) — anything
with no unresolved dependency on anything else in the same wave is,
by definition, safe to run in parallel.
"""

from __future__ import annotations

from jarvis.core.exceptions import CyclicDependencyError
from jarvis.core.planning.types import PlanTask

_INDEPENDENCE_MARKERS = ("meanwhile", "separately", "in parallel", "also", "additionally")


def estimate_sequential_dependencies(descriptions: list[str]) -> list[tuple[str, ...]]:
    """For each description (by index), which earlier indices (as
    string ids, "0".."n-1") it depends on. Sequential by default; a
    description containing an independence marker depends on nothing.
    """
    dependencies: list[tuple[str, ...]] = []
    for i, description in enumerate(descriptions):
        lowered = description.lower()
        if i == 0 or any(marker in lowered for marker in _INDEPENDENCE_MARKERS):
            dependencies.append(())
        else:
            dependencies.append((str(i - 1),))
    return dependencies


def topological_waves(tasks: list[PlanTask]) -> list[list[str]]:
    """Group task ids into waves: wave N's tasks all depend only on
    tasks in waves 0..N-1 (or nothing), so every task within one wave
    can run in parallel with the rest of that wave. Raises
    CyclicDependencyError if the dependency graph isn't a DAG.
    """
    remaining = {task.id: set(task.depends_on) for task in tasks}
    waves: list[list[str]] = []

    while remaining:
        ready = [
            task_id for task_id, deps in remaining.items() if not (deps & set(remaining))
        ]
        if not ready:
            raise CyclicDependencyError(
                f"cyclic or unresolved dependency among tasks: {sorted(remaining)}"
            )
        waves.append(sorted(ready))
        for task_id in ready:
            del remaining[task_id]

    return waves
