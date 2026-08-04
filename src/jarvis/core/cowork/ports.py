"""Abstract interfaces for the Cowork integration layer.

Two ports at two different layers, deliberately kept separate:

  - `CoworkTransport` is the low-level "send JSON, get JSON back"
    seam — the only place that knows about HTTP at all. This is what
    lets CoworkClient's retry/timeout/parsing logic (the actual
    "requirements" of this phase) be tested completely against a fake,
    with zero network dependency, the same "core logic depends on
    fakes, not a real backend" shape core/speech/'s StreamingTranscriber
    and SpeechQueue use.
  - `CoworkClientPort` is what the rest of Jarvis (eventually,
    Orchestrator) depends on: "submit a task, get a parsed response."
    It ships a Null Object default, `NullCoworkClientPort`, following
    every other port in this project — submit() never raises, it
    returns a response with an empty `steps` list, which reads to a
    caller exactly like "Cowork had nothing to add."
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

from jarvis.core.cowork.models import CoworkTaskRequest, CoworkTaskResponse

logger = logging.getLogger(__name__)


@runtime_checkable
class CoworkContextProvider(Protocol):
    """Supplies relevant memories to inject into a Cowork request's
    context before it's submitted (Phase 14) — "give Cowork only the
    relevant memories instead of the entire vault." Deliberately
    returns plain JSON-safe dicts, not a core/memory/ type: this
    Protocol lives in core/cowork/ so CoworkWorkspace (workspace.py)
    can depend on it without core/cowork/ ever importing core/memory/.
    core/memory/'s HybridMemorySearch.relevant_memories() satisfies this
    shape structurally, the same duck-typed relationship every other
    Protocol/implementation pair in this project has.
    """

    def relevant_memories(self, instruction: str, *, limit: int) -> list[dict[str, Any]]: ...


@runtime_checkable
class CoworkTransport(Protocol):
    """Sends one JSON POST and returns the parsed JSON body.

    Must raise `TimeoutError` if `timeout` elapses without a response,
    and any other exception on connection/HTTP-level failure — both are
    what CoworkClient's retry loop catches. Must not itself retry;
    retrying is CoworkClient's job so it can be tested and tuned in one
    place.
    """

    def post_json(
        self, path: str, payload: dict[str, Any], *, timeout: float
    ) -> dict[str, Any]: ...


@runtime_checkable
class CoworkClientPort(Protocol):
    """Submits a task to Cowork and returns its parsed response."""

    def submit(self, request: CoworkTaskRequest) -> CoworkTaskResponse: ...


class NullCoworkClientPort:
    """No Cowork backend configured. submit() always returns an empty
    plan rather than raising — callers (Orchestrator) treat that
    identically to "Cowork looked at this and had nothing to add,"
    which is the correct behavior when there's no real backend to ask.
    """

    def submit(self, request: CoworkTaskRequest) -> CoworkTaskResponse:
        logger.debug(
            "NullCoworkClientPort.submit(task_id=%r) — no Cowork backend configured",
            request.task_id,
        )
        return CoworkTaskResponse(
            task_id=request.task_id, summary="No Cowork backend configured", steps=[]
        )
