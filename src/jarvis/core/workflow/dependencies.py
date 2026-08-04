"""Wave-grouping over `WorkflowStep.depends_on` — "implement multi-step
automation" needs a deterministic run order, and grouping into waves
(rather than a flat topological sort) is what lets independent steps
within the same wave be dispatched together.

Same standard Kahn's-algorithm level-by-level sort as
`core/planning/dependencies.py`'s `topological_waves()`, reimplemented
here (rather than imported) because that one is coupled to
`core.planning.types.PlanTask` — a small, deliberate duplication in
favor of `core/workflow/` not depending on `core/planning/`'s domain
types, the same "own types per module" boundary this package's other
files follow.
"""

from __future__ import annotations

from jarvis.core.exceptions import CyclicWorkflowError
from jarvis.core.workflow.types import WorkflowStep


def topological_waves(steps: list[WorkflowStep]) -> list[list[str]]:
    """Group step ids into waves: wave N's steps all depend only on
    steps in waves 0..N-1 (or nothing). Raises CyclicWorkflowError if
    the dependency graph isn't a DAG.
    """
    remaining = {step.id: set(step.depends_on) for step in steps}
    waves: list[list[str]] = []

    while remaining:
        ready = [step_id for step_id, deps in remaining.items() if not (deps & set(remaining))]
        if not ready:
            raise CyclicWorkflowError(
                f"cyclic or unresolved dependency among workflow steps: {sorted(remaining)}"
            )
        waves.append(sorted(ready))
        for step_id in ready:
            del remaining[step_id]

    return waves
