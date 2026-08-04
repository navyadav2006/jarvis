from __future__ import annotations

from pathlib import Path

from jarvis.core.cowork.collaborators import CollaboratorRole
from jarvis.core.cowork.prompts import PromptRegistry


def test_renders_from_file_when_present(tmp_path: Path) -> None:
    (tmp_path / "coder.md").write_text(
        "Custom coder prompt for {instruction}.", encoding="utf-8"
    )
    registry = PromptRegistry(tmp_path)

    rendered = registry.render(
        CollaboratorRole.CODER, "fallback {instruction}", instruction="do X"
    )

    assert rendered == "Custom coder prompt for do X."


def test_falls_back_to_provided_template_when_file_missing(tmp_path: Path) -> None:
    registry = PromptRegistry(tmp_path)  # empty dir, no coder.md

    rendered = registry.render(
        CollaboratorRole.CODER, "fallback template: {instruction}", instruction="do X"
    )

    assert rendered == "fallback template: do X"


def test_falls_back_when_prompts_dir_does_not_exist(tmp_path: Path) -> None:
    registry = PromptRegistry(tmp_path / "does_not_exist")

    rendered = registry.render(
        CollaboratorRole.PLANNER, "fallback {instruction}", instruction="plan it"
    )

    assert rendered == "fallback plan it"


def test_system_md_is_prepended_when_present(tmp_path: Path) -> None:
    (tmp_path / "system.md").write_text("Shared boundary text.", encoding="utf-8")
    (tmp_path / "coder.md").write_text("Coder: {instruction}", encoding="utf-8")
    registry = PromptRegistry(tmp_path)

    rendered = registry.render(CollaboratorRole.CODER, "fallback", instruction="do X")

    assert rendered == "Shared boundary text.\n\nCoder: do X"


def test_no_system_md_means_no_preamble(tmp_path: Path) -> None:
    (tmp_path / "coder.md").write_text("Coder: {instruction}", encoding="utf-8")
    registry = PromptRegistry(tmp_path)

    rendered = registry.render(CollaboratorRole.CODER, "fallback", instruction="do X")

    assert rendered == "Coder: do X"


def test_context_placeholder_is_substituted(tmp_path: Path) -> None:
    (tmp_path / "researcher.md").write_text(
        "Q: {instruction}\nC: {context}", encoding="utf-8"
    )
    registry = PromptRegistry(tmp_path)

    rendered = registry.render(
        CollaboratorRole.RESEARCHER, "fallback", instruction="what is X", context="session s1"
    )

    assert rendered == "Q: what is X\nC: session s1"


def test_file_content_is_stripped_of_surrounding_whitespace(tmp_path: Path) -> None:
    (tmp_path / "coder.md").write_text("\n\n  Coder: {instruction}  \n\n", encoding="utf-8")
    registry = PromptRegistry(tmp_path)

    rendered = registry.render(CollaboratorRole.CODER, "fallback", instruction="do X")

    assert rendered == "Coder: do X"


def test_every_role_has_a_working_filename_mapping(tmp_path: Path) -> None:
    # A KeyError here would mean _FILENAMES is missing an entry for a
    # real CollaboratorRole -- this test fails loudly instead of only
    # surfacing the bug the first time that role is actually routed to.
    registry = PromptRegistry(tmp_path)
    for role in CollaboratorRole:
        rendered = registry.render(role, "fallback {instruction}", instruction="x")
        assert "fallback" in rendered
