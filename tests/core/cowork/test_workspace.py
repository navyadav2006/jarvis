from __future__ import annotations

from pathlib import Path

from jarvis.core.cowork.collaborators import CollaboratorRole
from jarvis.core.cowork.models import CoworkTaskRequest, CoworkTaskResponse
from jarvis.core.cowork.ports import CoworkClientPort
from jarvis.core.cowork.prompts import PromptRegistry
from jarvis.core.cowork.workspace import CoworkWorkspace, select_role


class RecordingCoworkClient:
    def __init__(self) -> None:
        self.received: list[CoworkTaskRequest] = []

    def submit(self, request: CoworkTaskRequest) -> CoworkTaskResponse:
        self.received.append(request)
        return CoworkTaskResponse(task_id=request.task_id, summary="ok")


def test_workspace_satisfies_cowork_client_port() -> None:
    assert isinstance(CoworkWorkspace(inner=RecordingCoworkClient()), CoworkClientPort)


def test_select_role_matches_keywords() -> None:
    assert select_role("please test this feature") == CollaboratorRole.QA_ENGINEER
    assert select_role("write documentation for the API") == CollaboratorRole.DOCUMENTATION_ENGINEER
    assert select_role("click the submit button") == CollaboratorRole.AUTOMATION_ENGINEER
    assert select_role("remember my favorite color") == CollaboratorRole.MEMORY_MANAGER
    assert select_role("research the best approach") == CollaboratorRole.RESEARCHER
    assert select_role("implement a parser") == CollaboratorRole.CODER
    assert select_role("design the architecture") == CollaboratorRole.ARCHITECT


def test_select_role_defaults_to_planner() -> None:
    assert select_role("do something entirely unrelated") == CollaboratorRole.PLANNER


def test_submit_routes_to_inner_client_with_rendered_prompt() -> None:
    inner = RecordingCoworkClient()
    workspace = CoworkWorkspace(inner=inner)

    workspace.submit(CoworkTaskRequest(session_id="s1", instruction="implement a parser"))

    assert len(inner.received) == 1
    routed = inner.received[0]
    assert routed.metadata["role"] == CollaboratorRole.CODER.value
    assert "implement a parser" in routed.instruction
    assert "You are the Coder" in routed.instruction


def test_submit_stamps_role_onto_response() -> None:
    inner = RecordingCoworkClient()
    workspace = CoworkWorkspace(inner=inner)

    response = workspace.submit(CoworkTaskRequest(session_id="s1", instruction="test this"))

    assert response.raw["role"] == CollaboratorRole.QA_ENGINEER.value


def test_explicit_role_in_metadata_overrides_keyword_selection() -> None:
    inner = RecordingCoworkClient()
    workspace = CoworkWorkspace(inner=inner)

    workspace.submit(
        CoworkTaskRequest(
            session_id="s1",
            instruction="implement a parser",  # would normally route to CODER
            metadata={"role": CollaboratorRole.ARCHITECT.value},
        )
    )

    assert inner.received[0].metadata["role"] == CollaboratorRole.ARCHITECT.value


class FakeContextProvider:
    def __init__(self, memories: list[dict]) -> None:
        self._memories = memories
        self.calls: list[tuple[str, int]] = []

    def relevant_memories(self, instruction: str, *, limit: int) -> list[dict]:
        self.calls.append((instruction, limit))
        return self._memories


def test_context_provider_injects_memories_into_request_context() -> None:
    inner = RecordingCoworkClient()
    provider = FakeContextProvider([{"content": "cats sleep a lot", "citation": "Notes/Cats.md"}])
    workspace = CoworkWorkspace(inner=inner, context_provider=provider, context_limit=3)

    workspace.submit(CoworkTaskRequest(session_id="s1", instruction="tell me about cats"))

    assert provider.calls == [("tell me about cats", 3)]
    assert inner.received[0].context["memories"] == [
        {"content": "cats sleep a lot", "citation": "Notes/Cats.md"}
    ]


def test_no_context_provider_leaves_context_untouched() -> None:
    inner = RecordingCoworkClient()
    workspace = CoworkWorkspace(inner=inner)

    workspace.submit(
        CoworkTaskRequest(session_id="s1", instruction="hello", context={"existing": "value"})
    )

    assert inner.received[0].context == {"existing": "value"}


def test_empty_memories_does_not_add_context_key() -> None:
    inner = RecordingCoworkClient()
    workspace = CoworkWorkspace(inner=inner, context_provider=FakeContextProvider([]))

    workspace.submit(CoworkTaskRequest(session_id="s1", instruction="hello"))

    assert "memories" not in inner.received[0].context


def test_prompt_registry_sources_the_rendered_prompt(tmp_path: Path) -> None:
    (tmp_path / "coder.md").write_text("File-backed coder: {instruction}", encoding="utf-8")
    inner = RecordingCoworkClient()
    workspace = CoworkWorkspace(inner=inner, prompt_registry=PromptRegistry(tmp_path))

    workspace.submit(CoworkTaskRequest(session_id="s1", instruction="implement a parser"))

    assert "File-backed coder: implement a parser" in inner.received[0].instruction


def test_no_prompt_registry_uses_hardcoded_templates() -> None:
    # Default behaviour (prompt_registry=None) is unchanged from Phase 10.
    inner = RecordingCoworkClient()
    workspace = CoworkWorkspace(inner=inner)

    workspace.submit(CoworkTaskRequest(session_id="s1", instruction="implement a parser"))

    assert "You are the Coder" in inner.received[0].instruction
