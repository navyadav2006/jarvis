"""CoworkWorkspace: Jarvis's orchestration of the eight collaborator
roles (Phase 10) on top of Phase 9's CoworkClientPort.

`CoworkWorkspace` itself implements `CoworkClientPort` (it has a
`submit()` method with the same signature), so it drops straight into
Orchestrator's existing `cowork` dependency with no signature change:
`main.bootstrap()` just wraps whatever backend it built (CoworkClient
or NullCoworkClientPort) in a CoworkWorkspace before handing it to
Orchestrator. The workspace's only job is picking *which collaborator*
to reason as and rendering its prompt — the actual network call, retry,
timeout, and parsing all still happen inside the wrapped
CoworkClientPort, unchanged from Phase 9. This is what "Jarvis
orchestrates these collaborators" means concretely: role selection is
Jarvis-owned code, not something Cowork decides for itself.

Phase 14 adds an optional `context_provider` (a `CoworkContextProvider`
— see ports.py): if given, every `submit()` call asks it for the
memories relevant to the request's instruction and merges them into
`request.context["memories"]` *before* the collaborator's prompt is
rendered, so injected memories are part of what Cowork actually sees.
Optional and off by default (`context_provider=None`) so existing
callers/tests are unaffected.

Phase 22 adds an optional `prompt_registry` (a `PromptRegistry` — see
prompts.py): if given, it's passed straight through to
`CollaboratorSpec.render_prompt()`, which sources each role's template
from `prompts/*.md` instead of the hardcoded Python string. Optional
and off by default for the same reason `context_provider` is.
"""

from __future__ import annotations

import logging

from jarvis.core.cowork.collaborators import COLLABORATOR_SPECS, CollaboratorRole
from jarvis.core.cowork.models import CoworkTaskRequest, CoworkTaskResponse
from jarvis.core.cowork.ports import CoworkClientPort, CoworkContextProvider
from jarvis.core.cowork.prompts import PromptRegistry

logger = logging.getLogger(__name__)

# Ordered so the first matching keyword wins; deliberately simple
# (keyword matching, not NLU) — good enough for "Jarvis decides which
# collaborator", not a claim of intelligent routing.
_ROLE_KEYWORDS: list[tuple[CollaboratorRole, tuple[str, ...]]] = [
    (CollaboratorRole.QA_ENGINEER, ("test", "verify", "review", "qa")),
    (CollaboratorRole.DOCUMENTATION_ENGINEER, ("document", "docs", "readme")),
    (CollaboratorRole.AUTOMATION_ENGINEER, ("click", "open", "automate", "type into")),
    (CollaboratorRole.MEMORY_MANAGER, ("remember", "recall", "forget")),
    (CollaboratorRole.RESEARCHER, ("research", "find out", "look up", "what is")),
    (CollaboratorRole.CODER, ("code", "implement", "write a function", "fix the bug")),
    (CollaboratorRole.ARCHITECT, ("design", "architecture", "approach")),
]
_DEFAULT_ROLE = CollaboratorRole.PLANNER


def select_role(instruction: str) -> CollaboratorRole:
    lowered = instruction.lower()
    for role, keywords in _ROLE_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return role
    return _DEFAULT_ROLE


class CoworkWorkspace:
    """Implements core.cowork.ports.CoworkClientPort."""

    def __init__(
        self,
        *,
        inner: CoworkClientPort,
        context_provider: CoworkContextProvider | None = None,
        context_limit: int = 5,
        prompt_registry: PromptRegistry | None = None,
    ) -> None:
        self._inner = inner
        self._context_provider = context_provider
        self._context_limit = context_limit
        self._prompt_registry = prompt_registry

    def submit(self, request: CoworkTaskRequest) -> CoworkTaskResponse:
        if self._context_provider is not None:
            memories = self._context_provider.relevant_memories(
                request.instruction, limit=self._context_limit
            )
            if memories:
                request = request.model_copy(
                    update={"context": {**request.context, "memories": memories}}
                )

        requested_role = request.metadata.get("role")
        valid_roles = {r.value for r in CollaboratorRole}
        role = (
            CollaboratorRole(requested_role)
            if requested_role in valid_roles
            else select_role(request.instruction)
        )
        spec = COLLABORATOR_SPECS[role]

        rendered = spec.render_prompt(
            instruction=request.instruction,
            context=str(request.context),
            registry=self._prompt_registry,
        )
        logger.debug("CoworkWorkspace routing task %s to %s", request.task_id, role.value)

        routed_request = request.model_copy(
            update={
                "instruction": rendered,
                "metadata": {**request.metadata, "role": role.value},
            }
        )
        response = self._inner.submit(routed_request)
        return response.model_copy(update={"raw": {**response.raw, "role": role.value}})
