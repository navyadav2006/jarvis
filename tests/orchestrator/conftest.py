from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core.cowork.models import CoworkTaskRequest, CoworkTaskResponse
from jarvis.core.cowork.ports import NullCoworkClientPort
from jarvis.core.events import EventBus
from jarvis.core.filesystem.port import FileOperationResult
from jarvis.orchestrator.capability_registry import CapabilityRegistry
from jarvis.orchestrator.intent_recognizer import PatternIntentRecognizer
from jarvis.orchestrator.models import Turn
from jarvis.orchestrator.orchestrator import Orchestrator
from jarvis.orchestrator.ports import AutomationAction, AutomationResult, MemoryItem
from jarvis.orchestrator.session_store import SessionStore


class FakeMemoryPort:
    """Test double proving MemoryPort is satisfied structurally — no
    inheritance from anything in ports.py is required.
    """

    def __init__(self, *, raises: Exception | None = None) -> None:
        self.remembered: list[tuple[str, Turn]] = []
        self.recall_response: list[MemoryItem] = []
        self._raises = raises

    def recall(self, session_id: str, query: str, *, limit: int = 5) -> list[MemoryItem]:
        if self._raises is not None:
            raise self._raises
        return self.recall_response

    def remember(self, session_id: str, turn: Turn) -> None:
        if self._raises is not None:
            raise self._raises
        self.remembered.append((session_id, turn))


class FakeAutomationPort:
    def __init__(self) -> None:
        self.executed: list[AutomationAction] = []

    def execute(self, action: AutomationAction) -> AutomationResult:
        self.executed.append(action)
        return AutomationResult(success=True, output="done")


class FakeFilesystemPort:
    """Test double proving FilesystemPort is satisfied structurally, just
    like FakeMemoryPort/FakeAutomationPort above.
    """

    def __init__(self) -> None:
        self.files: dict[str, str] = {}
        self.calls: list[tuple[str, tuple]] = []

    def read(self, path) -> str:
        self.calls.append(("read", (path,)))
        return self.files[str(path)]

    def write(self, path, content: str, *, confirmed: bool = False) -> FileOperationResult:
        self.calls.append(("write", (path, content)))
        self.files[str(path)] = content
        return FileOperationResult(operation="write", success=True, path=Path(path))

    def copy(self, source, destination, *, confirmed: bool = False) -> FileOperationResult:
        self.calls.append(("copy", (source, destination)))
        return FileOperationResult(
            operation="copy", success=True, path=Path(source), destination=Path(destination)
        )

    def move(self, source, destination, *, confirmed: bool = False) -> FileOperationResult:
        self.calls.append(("move", (source, destination)))
        return FileOperationResult(
            operation="move", success=True, path=Path(source), destination=Path(destination)
        )

    def rename(self, path, new_name: str, *, confirmed: bool = False) -> FileOperationResult:
        self.calls.append(("rename", (path, new_name)))
        return FileOperationResult(operation="rename", success=True, path=Path(path))

    def delete(self, path, *, confirmed: bool = False) -> FileOperationResult:
        self.calls.append(("delete", (path,)))
        return FileOperationResult(operation="delete", success=True, path=Path(path))

    def search(self, directory, pattern: str, *, recursive: bool = True) -> list[Path]:
        self.calls.append(("search", (directory, pattern)))
        return []


class FakeCoworkClient:
    """A CoworkClientPort test double: returns a pre-set response (or
    raises a pre-set exception) regardless of the request submitted.
    """

    def __init__(
        self, response: CoworkTaskResponse | None = None, *, raises: Exception | None = None
    ) -> None:
        self._response = response
        self._raises = raises
        self.submitted: list[CoworkTaskRequest] = []

    def submit(self, request: CoworkTaskRequest) -> CoworkTaskResponse:
        self.submitted.append(request)
        if self._raises is not None:
            raise self._raises
        assert self._response is not None
        return self._response


@pytest.fixture
def capability_registry() -> CapabilityRegistry:
    return CapabilityRegistry()


@pytest.fixture
def session_store() -> SessionStore:
    return SessionStore()


@pytest.fixture
def intent_recognizer(capability_registry: CapabilityRegistry) -> PatternIntentRecognizer:
    return PatternIntentRecognizer(capability_registry)


@pytest.fixture
def fake_memory() -> FakeMemoryPort:
    return FakeMemoryPort()


@pytest.fixture
def fake_automation() -> FakeAutomationPort:
    return FakeAutomationPort()


@pytest.fixture
def fake_filesystem() -> FakeFilesystemPort:
    return FakeFilesystemPort()


@pytest.fixture
def orchestrator(
    event_bus: EventBus,
    capability_registry: CapabilityRegistry,
    intent_recognizer: PatternIntentRecognizer,
    session_store: SessionStore,
    fake_memory: FakeMemoryPort,
    fake_automation: FakeAutomationPort,
    fake_filesystem: FakeFilesystemPort,
) -> Orchestrator:
    return Orchestrator(
        events=event_bus,
        capability_registry=capability_registry,
        intent_recognizer=intent_recognizer,
        session_store=session_store,
        memory=fake_memory,
        automation=fake_automation,
        filesystem=fake_filesystem,
        cowork=NullCoworkClientPort(),
    )
