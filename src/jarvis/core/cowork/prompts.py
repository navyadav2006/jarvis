"""PromptRegistry: loads collaborator prompt templates from
version-controlled Markdown files under `prompts/` instead of the
hardcoded Python strings `collaborators.py`'s `COLLABORATOR_SPECS`
shipped with since Phase 10 — refining one collaborator's behavior
becomes a text edit, reviewable in git alongside the rest of the
project, not a code change.

Reads each file fresh on every `render()` call — no caching, no
watcher thread. "Dynamically load these prompt templates when invoking
the corresponding collaborator" is satisfied by simply reading at call
time: a `prompts/*.md` edit takes effect on the very next Cowork
request, no restart needed, the simplest version of "dynamic" that's
still correct (this project's live-reload elsewhere, e.g.
`ConfigManager`, exists to detect changes on an *idle* process; a
Cowork request already reads from disk once per call, so there's
nothing extra to build here).

Falls back to `CollaboratorSpec.prompt_template` (Phase 10, still
present, unchanged) when `prompts/` or a specific role's file is
missing — so a checkout with no `prompts/` directory populated yet, or
a test that doesn't wire a registry in at all, behaves exactly as
before this phase. This is the same "real file wins, hardcoded default
is the safety net" shape `core/config/`'s YAML-with-defaults already
uses, applied to prompt text instead of settings.

`system.md`, if present, is prepended to every rendered prompt as a
shared preamble — currently the one boundary every collaborator's
Python `boundaries` metadata already documents
("Never execute anything directly; only return data for Jarvis to act
on"), but which, before this phase, was never actually part of the
text sent to Cowork, only Python-side self-documentation. Moving it
into `system.md` makes it a real, literal part of every collaborator's
prompt — a small defense-in-depth improvement, on top of (not instead
of) the structural guarantee that already makes it true regardless of
prompt wording: `CoworkPlanStep` has no `execute()` method, so nothing
Cowork returns can act on its own no matter what a prompt says.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jarvis.core.cowork.collaborators import CollaboratorRole

logger = logging.getLogger(__name__)

SYSTEM_FILENAME = "system.md"

# CollaboratorRole.value -> filename. Not simply f"{role.value}.md" for
# three roles (memory_manager/documentation_engineer/qa_engineer) --
# shorter names read better as files than the full enum value does.
_FILENAMES: dict[str, str] = {
    "architect": "architect.md",
    "planner": "planner.md",
    "coder": "coder.md",
    "researcher": "researcher.md",
    "memory_manager": "memory.md",
    "automation_engineer": "automation_engineer.md",
    "documentation_engineer": "documentation.md",
    "qa_engineer": "qa.md",
}


class PromptRegistry:
    def __init__(self, prompts_dir: Path) -> None:
        self._dir = Path(prompts_dir)

    def render(
        self,
        role: CollaboratorRole,
        fallback_template: str,
        *,
        instruction: str,
        context: str = "",
    ) -> str:
        template = self._read(_FILENAMES[role.value]) or fallback_template
        body = template.format(instruction=instruction, context=context)
        system = self._read(SYSTEM_FILENAME)
        return f"{system}\n\n{body}" if system else body

    def _read(self, filename: str) -> str | None:
        path = self._dir / filename
        if not path.is_file():
            return None
        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError:
            logger.warning("Failed to read prompt file %s; falling back", path, exc_info=True)
            return None
