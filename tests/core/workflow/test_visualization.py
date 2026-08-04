from __future__ import annotations

from jarvis.core.workflow.types import (
    Workflow,
    WorkflowRun,
    WorkflowStatus,
    WorkflowStep,
    WorkflowStepResult,
    WorkflowStepStatus,
    WorkflowTrigger,
)
from jarvis.core.workflow.visualization import to_mermaid


def _workflow() -> Workflow:
    return Workflow(
        id="w1",
        name="demo",
        steps=[
            WorkflowStep(id="a", name='Step "A"', action="x.y"),
            WorkflowStep(id="b", name="Step B", action="x.y", depends_on=("a",)),
        ],
    )


def test_to_mermaid_without_a_run_has_no_status_classes() -> None:
    mermaid = to_mermaid(_workflow())
    assert "flowchart TD" in mermaid
    assert 'a["Step \'A\'"]' in mermaid
    assert "a --> b" in mermaid
    assert "classDef" not in mermaid


def test_to_mermaid_with_a_run_colors_by_status() -> None:
    run = WorkflowRun(
        id="r1",
        workflow_id="w1",
        trigger=WorkflowTrigger.MANUAL,
        status=WorkflowStatus.FAILED,
        step_results={
            "a": WorkflowStepResult(step_id="a", status=WorkflowStepStatus.SUCCEEDED),
            "b": WorkflowStepResult(step_id="b", status=WorkflowStepStatus.FAILED),
        },
    )
    mermaid = to_mermaid(_workflow(), run)
    assert "classDef succeeded" in mermaid
    assert "class a succeeded;" in mermaid
    assert "class b failed;" in mermaid
