# Prompt Registry

Version-controlled Markdown prompt templates for each Cowork
collaborator role (`core/cowork/collaborators.py`'s `CollaboratorRole`,
Phase 10), loaded dynamically by `PromptRegistry`
(`core/cowork/prompts.py`, Phase 22) every time `CoworkWorkspace`
routes a request to a collaborator. Edit a file here and the change
takes effect on the next Cowork request — no restart, no code change.

| File | Collaborator |
|---|---|
| `system.md` | Prepended to every collaborator's rendered prompt |
| `architect.md` | Architect |
| `planner.md` | Planner |
| `coder.md` | Coder |
| `researcher.md` | Researcher |
| `memory.md` | Memory Manager |
| `automation_engineer.md` | Automation Engineer |
| `documentation.md` | Documentation Engineer |
| `qa.md` | QA Engineer |

Each role file must contain `{instruction}` and `{context}` — filled
in via Python `str.format()` when the prompt is rendered. `system.md`
does not take placeholders; it's static text prepended as-is.

If a file here is missing (or this directory doesn't exist), Jarvis
falls back to the built-in template in `COLLABORATOR_SPECS`
(`core/cowork/collaborators.py`) for that role, so deleting a file
doesn't break anything — it just reverts that one collaborator to its
default prompt.

There's deliberately no `orchestrator.md`, `security.md`, `browser.md`,
or `desktop.md`: Jarvis's `Orchestrator` (intent routing) and
`SecurityManager` are local Python logic with no LLM prompt to
externalize, and there's currently one `automation_engineer` role
covering both desktop and browser automation rather than two separate
roles — see `docs/architecture.md`'s Phase 22 section if that split
becomes worth doing later.
