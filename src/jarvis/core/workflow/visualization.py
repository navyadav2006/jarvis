""""Generate workflow visualisations": a Mermaid flowchart of a
workflow's steps and dependencies, optionally colored by a run's
per-step status. Text output (a `.mmd`-compatible string), matching
this project's existing preference for markdown/mermaid over a binary
image format — `docs/architecture.md` already embeds mermaid diagrams
by hand; this is the same format, generated.
"""

from __future__ import annotations

from jarvis.core.workflow.types import Workflow, WorkflowRun, WorkflowStepStatus

_STATUS_CLASS = {
    WorkflowStepStatus.SUCCEEDED: "succeeded",
    WorkflowStepStatus.FAILED: "failed",
    WorkflowStepStatus.RUNNING: "running",
    WorkflowStepStatus.SKIPPED: "skipped",
    WorkflowStepStatus.PENDING: "pending",
}

_CLASS_DEFS = (
    "    classDef succeeded fill:#3fb950,color:#fff;\n"
    "    classDef failed fill:#f85149,color:#fff;\n"
    "    classDef running fill:#d29922,color:#000;\n"
    "    classDef skipped fill:#8b949e,color:#fff;\n"
    "    classDef pending fill:#30363d,color:#fff;"
)


def _escape(text: str) -> str:
    return text.replace('"', "'")


def to_mermaid(workflow: Workflow, run: WorkflowRun | None = None) -> str:
    lines = ["flowchart TD"]

    for step in workflow.steps:
        lines.append(f'    {step.id}["{_escape(step.name)}"]')

    for step in workflow.steps:
        for dep in step.depends_on:
            lines.append(f"    {dep} --> {step.id}")

    if run is not None:
        lines.append(_CLASS_DEFS)
        for step in workflow.steps:
            result = run.step_results.get(step.id)
            if result is not None:
                lines.append(f"    class {step.id} {_STATUS_CLASS[result.status]};")

    return "\n".join(lines)
