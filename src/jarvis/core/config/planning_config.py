"""planning.yaml — the Planning Engine's settings (Phase 17): retry
policy and the heuristic that decides when Jarvis should display a
plan before executing it.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

PLANNING_FILENAME = "planning.yaml"


class PlanningConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_retries: int = Field(2, ge=0)

    # "Display the plan before execution when appropriate": a plan is
    # shown for preview when it has more than this many tasks, OR
    # touches one of `preview_risky_collaborators` below.
    preview_task_threshold: int = Field(3, ge=1)
    preview_risky_collaborators: list[str] = Field(
        default_factory=lambda: ["automation_engineer"]
    )
    # Task descriptions containing any of these words also force a
    # preview, regardless of size/collaborator — a one-task "delete
    # everything" plan deserves a look just as much as a five-task one.
    preview_risky_keywords: list[str] = Field(
        default_factory=lambda: ["delete", "remove", "overwrite", "purchase", "pay", "send"]
    )
