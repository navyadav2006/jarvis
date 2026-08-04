from __future__ import annotations

from pathlib import Path

from jarvis.core.cowork.collaborators import COLLABORATOR_SPECS, CollaboratorRole
from jarvis.core.cowork.prompts import PromptRegistry

EXPECTED_ROLES = {
    CollaboratorRole.ARCHITECT,
    CollaboratorRole.PLANNER,
    CollaboratorRole.CODER,
    CollaboratorRole.RESEARCHER,
    CollaboratorRole.MEMORY_MANAGER,
    CollaboratorRole.AUTOMATION_ENGINEER,
    CollaboratorRole.DOCUMENTATION_ENGINEER,
    CollaboratorRole.QA_ENGINEER,
}


def test_all_eight_required_roles_are_defined() -> None:
    assert set(COLLABORATOR_SPECS.keys()) == EXPECTED_ROLES


def test_every_spec_has_responsibilities_boundaries_and_template() -> None:
    for role, spec in COLLABORATOR_SPECS.items():
        assert spec.role == role
        assert len(spec.responsibilities) >= 1
        assert len(spec.boundaries) >= 1
        assert "{instruction}" in spec.prompt_template


def test_every_boundary_forbids_direct_execution() -> None:
    for spec in COLLABORATOR_SPECS.values():
        assert any("execute" in b.lower() or "directly" in b.lower() for b in spec.boundaries)


def test_render_prompt_substitutes_instruction_and_context() -> None:
    spec = COLLABORATOR_SPECS[CollaboratorRole.CODER]
    rendered = spec.render_prompt(instruction="write a parser", context="session s1")
    assert "write a parser" in rendered
    assert "session s1" in rendered


def test_render_prompt_with_no_registry_uses_hardcoded_template() -> None:
    # Phase 22's PromptRegistry is fully optional -- render_prompt()
    # without one must behave exactly as it did in Phase 10.
    spec = COLLABORATOR_SPECS[CollaboratorRole.CODER]
    rendered = spec.render_prompt(instruction="write a parser")
    assert rendered == spec.prompt_template.format(instruction="write a parser", context="")


def test_render_prompt_with_registry_uses_file_backed_template(tmp_path: Path) -> None:
    (tmp_path / "coder.md").write_text("File-backed: {instruction}", encoding="utf-8")
    registry = PromptRegistry(tmp_path)
    spec = COLLABORATOR_SPECS[CollaboratorRole.CODER]

    rendered = spec.render_prompt(instruction="write a parser", registry=registry)

    assert rendered == "File-backed: write a parser"
