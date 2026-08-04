"""Strongly typed messages exchanged with Claude Cowork.

Pydantic `BaseModel`s, not the plain dataclasses orchestrator/models.py
uses elsewhere — these types cross a real serialization boundary (JSON
over HTTP), so validating shape at the boundary (via `model_validate`)
is the point, not just convenient typing. All frozen: a task request or
response is a fact about one exchange, never mutated after construction,
the same "config is a value" convention core/config/'s models follow.

`CoworkPlanStep` is deliberately inert data. It can *describe* an
automation action (`AutomationActionModel`); it cannot perform one —
there is no `execute()` method anywhere in this module. That is the
whole enforcement mechanism behind "Claude Cowork must never directly
manipulate the operating system": Cowork's only output is a value
Jarvis's orchestrator chooses whether and how to act on, via the
existing AutomationPort/FilesystemPort ports (core/orchestrator/ports.py),
never via anything Cowork itself holds a reference to.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AutomationActionModel(BaseModel):
    """Wire format for orchestrator.ports.AutomationAction — kept as a
    separate model (rather than reusing the dataclass directly) so this
    module has no import-time dependency on orchestrator/, matching the
    "core never depends on orchestrator" rule from Phase 2.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class CoworkPlanStep(BaseModel):
    """One step of Cowork's plan. `action_type` is closed to what Jarvis
    already knows how to execute locally — Cowork cannot introduce a
    new kind of action Jarvis wasn't already capable of performing.
    """

    model_config = ConfigDict(frozen=True)

    step_id: int
    description: str
    action_type: Literal["automation", "respond"]
    automation: AutomationActionModel | None = None
    response_text: str | None = None


class CoworkTaskRequest(BaseModel):
    """The task message Jarvis sends to Cowork: the request text plus
    enough session context for Cowork to reason about it, and nothing
    that would let it act — there is no port/handle in this model.
    """

    model_config = ConfigDict(frozen=True)

    task_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    session_id: str
    instruction: str
    context: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CoworkTaskResponse(BaseModel):
    """Cowork's answer: a summary plus zero or more plan steps for
    Jarvis to execute locally. An empty `steps` list means "Cowork has
    nothing actionable to add" — NullCoworkClientPort's response always
    looks like this, so Orchestrator's fallback-to-unhandled path
    doesn't need to special-case "no backend configured" separately
    from "Cowork declined this task."
    """

    model_config = ConfigDict(frozen=True)

    task_id: str
    summary: str
    steps: list[CoworkPlanStep] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class CoworkDiagnostics(BaseModel):
    """One request's outcome, for logging/observability — not sent over
    the wire. CoworkClient records the most recent one and publishes it
    on the EventBus so nothing needs to inspect exceptions to know
    "how many retries did that take, how long did it take."
    """

    model_config = ConfigDict(frozen=True)

    task_id: str
    attempts: int
    latency_ms: float
    status: Literal["success", "timeout", "error"]
    error: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
