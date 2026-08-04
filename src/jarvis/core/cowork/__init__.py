"""The Cowork integration layer (Phase 9): Jarvis's client for Claude
Cowork, its collaborative-reasoning engine.

Jarvis is a system-wide AI operating layer, not a single-agent
assistant: local capability handlers answer what they can, and
whatever they can't is offered to Cowork for planning. Cowork responds
with a structured, inert plan (CoworkTaskResponse) — it has no access
to any port capable of touching the filesystem, desktop, browser, or
terminal. Only Jarvis's orchestrator, using the same AutomationPort/
FilesystemPort it already depends on, ever executes anything. This
module cannot violate that boundary even by accident: nothing here
imports orchestrator/, and CoworkTaskResponse/CoworkPlanStep
(models.py) have no methods, only data.

`CoworkTransport` (the HTTP layer) is separated from `CoworkClient`
(retry/timeout/parsing/diagnostics) specifically so the latter — this
phase's actual requirements — is fully unit-testable against a fake
transport, with zero network dependency, the same pattern
core/speech/'s StreamingTranscriber and SpeechQueue use for buffering
logic versus real backends. `httpx` (HttpCoworkTransport's only
dependency) is imported lazily, so `import jarvis.core.cowork` always
succeeds.

Not wired into `main.py` or the orchestrator — see
docs/architecture.md's Phase 9 section for what's deliberately deferred.
"""

from __future__ import annotations

from jarvis.core.cowork.client import CoworkClient
from jarvis.core.cowork.collaborators import (
    COLLABORATOR_SPECS,
    CollaboratorOutput,
    CollaboratorRole,
    CollaboratorSpec,
)
from jarvis.core.cowork.http_transport import HttpCoworkTransport
from jarvis.core.cowork.models import (
    AutomationActionModel,
    CoworkDiagnostics,
    CoworkPlanStep,
    CoworkTaskRequest,
    CoworkTaskResponse,
)
from jarvis.core.cowork.ports import (
    CoworkClientPort,
    CoworkContextProvider,
    CoworkTransport,
    NullCoworkClientPort,
)
from jarvis.core.cowork.prompts import PromptRegistry
from jarvis.core.cowork.workspace import CoworkWorkspace, select_role

__all__ = [
    "AutomationActionModel",
    "COLLABORATOR_SPECS",
    "CollaboratorOutput",
    "CollaboratorRole",
    "CollaboratorSpec",
    "CoworkClient",
    "CoworkClientPort",
    "CoworkContextProvider",
    "CoworkDiagnostics",
    "CoworkPlanStep",
    "CoworkTaskRequest",
    "CoworkTaskResponse",
    "CoworkTransport",
    "CoworkWorkspace",
    "HttpCoworkTransport",
    "NullCoworkClientPort",
    "PromptRegistry",
    "select_role",
]
