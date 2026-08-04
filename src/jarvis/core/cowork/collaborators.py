"""Collaborator specs for the internal Cowork workspace (Phase 10).

A "collaborator" is not a separate agent process — it's a named role
Cowork is asked to reason *as*, via a rendered prompt template, before
Jarvis submits the task through the same `CoworkClientPort` from
Phase 9. Every collaborator's boundary is enforced the same structural
way Phase 9 already established: `CollaboratorOutput.steps` is a list
of `CoworkPlanStep`, which has no method that could touch the
filesystem, desktop, browser, or terminal. Whatever role Cowork
reasoned as, only `Orchestrator._try_cowork()` ever executes a step,
via `AutomationPort`.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from jarvis.core.cowork.models import CoworkPlanStep

if TYPE_CHECKING:
    from jarvis.core.cowork.prompts import PromptRegistry


class CollaboratorRole(StrEnum):
    ARCHITECT = "architect"
    PLANNER = "planner"
    CODER = "coder"
    RESEARCHER = "researcher"
    MEMORY_MANAGER = "memory_manager"
    AUTOMATION_ENGINEER = "automation_engineer"
    DOCUMENTATION_ENGINEER = "documentation_engineer"
    QA_ENGINEER = "qa_engineer"


class CollaboratorSpec(BaseModel):
    """One collaborator's definition: what it's for, what it must never
    do, and the reusable prompt template used to invoke it.
    """

    model_config = ConfigDict(frozen=True)

    role: CollaboratorRole
    responsibilities: list[str]
    boundaries: list[str]
    prompt_template: str  # formatted with {instruction} and {context}

    def render_prompt(
        self,
        *,
        instruction: str,
        context: str = "",
        registry: PromptRegistry | None = None,
    ) -> str:
        """Renders this role's prompt. When `registry` is given (Phase
        22's PromptRegistry), the template comes from `prompts/*.md`,
        falling back to `prompt_template` below if the file is
        missing; with no registry, `prompt_template` is used directly
        — unchanged from Phase 10, so existing callers/tests that
        don't wire a registry in are unaffected.
        """
        if registry is not None:
            return registry.render(
                self.role, self.prompt_template, instruction=instruction, context=context
            )
        return self.prompt_template.format(instruction=instruction, context=context)


class CollaboratorOutput(BaseModel):
    """What a collaborator produces — the same inert-plan shape every
    Cowork response uses (CoworkTaskResponse), scoped to one role, so
    Orchestrator/CoworkWorkspace never need a second execution path.
    """

    model_config = ConfigDict(frozen=True)

    role: CollaboratorRole
    summary: str
    steps: list[CoworkPlanStep] = Field(default_factory=list)


_BASE_BOUNDARY = (
    "Never execute anything directly; only return data for Jarvis to act on."
)

COLLABORATOR_SPECS: dict[CollaboratorRole, CollaboratorSpec] = {
    CollaboratorRole.ARCHITECT: CollaboratorSpec(
        role=CollaboratorRole.ARCHITECT,
        responsibilities=[
            "Propose a technical approach/design for the request.",
            "Identify trade-offs and risks before implementation starts.",
        ],
        boundaries=[
            _BASE_BOUNDARY,
            "Never writes final code — hands design decisions to Coder/Planner.",
        ],
        prompt_template=(
            "You are the Architect. Propose a technical design for this request. "
            "Do not write implementation code and do not propose executing anything "
            "yourself — describe the approach only.\n\nRequest: {instruction}\n"
            "Context: {context}"
        ),
    ),
    CollaboratorRole.PLANNER: CollaboratorSpec(
        role=CollaboratorRole.PLANNER,
        responsibilities=[
            "Break a request (or an Architect design) into an ordered list of steps.",
            "Map each step to an action_type Jarvis already knows how to execute.",
        ],
        boundaries=[
            _BASE_BOUNDARY,
            "Never invents an action_type Jarvis doesn't already support "
            "(only 'automation' and 'respond' exist as of Phase 9).",
        ],
        prompt_template=(
            "You are the Planner. Break this request into an ordered list of steps, "
            "each tagged with an action_type Jarvis supports ('automation' or "
            "'respond'). Do not execute anything yourself.\n\nRequest: {instruction}\n"
            "Context: {context}"
        ),
    ),
    CollaboratorRole.CODER: CollaboratorSpec(
        role=CollaboratorRole.CODER,
        responsibilities=[
            "Produce code or file content as text for Jarvis to write via FilesystemPort.",
        ],
        boundaries=[
            _BASE_BOUNDARY,
            "Never runs code and never writes to disk itself — content only.",
        ],
        prompt_template=(
            "You are the Coder. Produce the requested code/content as text. Do not "
            "run it and do not write it to disk yourself — Jarvis will.\n\n"
            "Request: {instruction}\nContext: {context}"
        ),
    ),
    CollaboratorRole.RESEARCHER: CollaboratorSpec(
        role=CollaboratorRole.RESEARCHER,
        responsibilities=[
            "Synthesize an answer from the context Jarvis provides.",
        ],
        boundaries=[
            _BASE_BOUNDARY,
            "Never browses the web or filesystem itself — relies only on supplied context.",
        ],
        prompt_template=(
            "You are the Researcher. Answer using only the supplied context — you "
            "have no browser or filesystem access of your own.\n\n"
            "Request: {instruction}\nContext: {context}"
        ),
    ),
    CollaboratorRole.MEMORY_MANAGER: CollaboratorSpec(
        role=CollaboratorRole.MEMORY_MANAGER,
        responsibilities=[
            "Recommend what should be recalled or remembered for this request.",
        ],
        boundaries=[
            _BASE_BOUNDARY,
            "Never reads or writes memory itself — only recommends recall/remember/forget "
            "actions. The real memory operations happen in core/memory/'s "
            "MemoryManagerPort (Phase 12), called by Jarvis directly, not by this role.",
        ],
        prompt_template=(
            "You are the Memory Manager. Recommend what should be recalled or "
            "remembered for this request. You cannot access memory directly.\n\n"
            "Request: {instruction}\nContext: {context}"
        ),
    ),
    CollaboratorRole.AUTOMATION_ENGINEER: CollaboratorSpec(
        role=CollaboratorRole.AUTOMATION_ENGINEER,
        responsibilities=[
            "Translate a goal into a sequence of automation plan steps "
            "(desktop/browser actions).",
        ],
        boundaries=[
            _BASE_BOUNDARY,
            "Never invokes AutomationPort itself — only describes steps for Jarvis to run.",
        ],
        prompt_template=(
            "You are the Automation Engineer. Describe the desktop/browser automation "
            "steps needed, as data only — you cannot control input devices or "
            "applications yourself.\n\nRequest: {instruction}\nContext: {context}"
        ),
    ),
    CollaboratorRole.DOCUMENTATION_ENGINEER: CollaboratorSpec(
        role=CollaboratorRole.DOCUMENTATION_ENGINEER,
        responsibilities=[
            "Produce documentation content/updates as text.",
        ],
        boundaries=[
            _BASE_BOUNDARY,
            "Never writes files directly — content only, Jarvis performs the write.",
        ],
        prompt_template=(
            "You are the Documentation Engineer. Produce the requested documentation "
            "as text. Do not write it to disk yourself.\n\n"
            "Request: {instruction}\nContext: {context}"
        ),
    ),
    CollaboratorRole.QA_ENGINEER: CollaboratorSpec(
        role=CollaboratorRole.QA_ENGINEER,
        responsibilities=[
            "Review a proposed plan/output for correctness and safety issues "
            "before Jarvis executes it.",
        ],
        boundaries=[
            _BASE_BOUNDARY,
            "Cannot modify or execute the plan itself — only annotates/flags issues.",
        ],
        prompt_template=(
            "You are the QA Engineer. Review the following for correctness and safety "
            "issues. Do not modify or execute anything — report findings only.\n\n"
            "Request: {instruction}\nContext: {context}"
        ),
    ),
}
