"""The Autonomous Workflow engine (Phase 20): scheduled/recurring
multi-step automation with conditional execution, background
execution, durable history, editable definitions, Cowork-generated
plans, and Mermaid visualisations — all sequenced through
`WorkflowEngine` and gated, in production, by whatever already
enforces Phase 19's SecurityManager on every automation action.

See `engine.py`'s module docstring for the full execution model and
docs/architecture.md's Phase 20 section for the full design rationale.
"""

from __future__ import annotations

from jarvis.core.workflow.conditions import evaluate_condition
from jarvis.core.workflow.cron import CronSchedule, next_run_after
from jarvis.core.workflow.dependencies import topological_waves
from jarvis.core.workflow.engine import WorkflowEngine
from jarvis.core.workflow.ports import WorkflowActionPort, WorkflowActionResult, WorkflowStorePort
from jarvis.core.workflow.runner import WorkflowRunner
from jarvis.core.workflow.scheduler import WorkflowScheduler
from jarvis.core.workflow.store import SqliteWorkflowStore
from jarvis.core.workflow.types import (
    ConditionType,
    Workflow,
    WorkflowCondition,
    WorkflowRun,
    WorkflowSchedule,
    WorkflowStatus,
    WorkflowStep,
    WorkflowStepResult,
    WorkflowStepStatus,
    WorkflowTrigger,
)
from jarvis.core.workflow.validation import validate_schedule, validate_steps
from jarvis.core.workflow.visualization import to_mermaid

__all__ = [
    "ConditionType",
    "CronSchedule",
    "SqliteWorkflowStore",
    "Workflow",
    "WorkflowActionPort",
    "WorkflowActionResult",
    "WorkflowCondition",
    "WorkflowEngine",
    "WorkflowRun",
    "WorkflowRunner",
    "WorkflowSchedule",
    "WorkflowScheduler",
    "WorkflowStatus",
    "WorkflowStep",
    "WorkflowStepResult",
    "WorkflowStepStatus",
    "WorkflowStorePort",
    "WorkflowTrigger",
    "evaluate_condition",
    "next_run_after",
    "to_mermaid",
    "topological_waves",
    "validate_schedule",
    "validate_steps",
]
