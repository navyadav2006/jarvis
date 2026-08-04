from __future__ import annotations

from jarvis.core.container import ServiceContainer
from jarvis.core.events import EventBus
from jarvis.orchestrator.models import CapabilityContext, Intent, Request, Session


def make_context(
    *, text: str = "hello", session_id: str = "s1", metadata: dict | None = None, **ports
) -> CapabilityContext:
    return CapabilityContext(
        request=Request(text=text, session_id=session_id, metadata=metadata or {}),
        intent=Intent(name="test", confidence=1.0, raw_text=text),
        session=Session(session_id=session_id),
        memory=ports.get("memory"),
        automation=ports.get("automation"),
        filesystem=ports.get("filesystem"),
        recalled=[],
    )


def make_container_and_events() -> tuple[ServiceContainer, EventBus]:
    return ServiceContainer(), EventBus()
