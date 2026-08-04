"""End-to-end proof that a plugin can add a capability the orchestrator
routes to, using only what the ServiceContainer gives it — no import of
Orchestrator, no import of any orchestrator internals beyond the
CapabilityRegistry/CapabilityContext/CapabilityResult shapes every
plugin author needs.
"""

from __future__ import annotations

from jarvis.core.config.filesystem_config import FilesystemConfig
from jarvis.core.container import ServiceContainer
from jarvis.core.cowork.ports import NullCoworkClientPort
from jarvis.core.events import EventBus
from jarvis.core.filesystem import LocalFilesystemService
from jarvis.orchestrator.capability_registry import CapabilityRegistry
from jarvis.orchestrator.intent_recognizer import PatternIntentRecognizer
from jarvis.orchestrator.models import CapabilityContext, CapabilityResult, Request
from jarvis.orchestrator.orchestrator import Orchestrator
from jarvis.orchestrator.ports import NullAutomationPort, NullMemoryPort
from jarvis.orchestrator.session_store import SessionStore
from jarvis.plugins.base import PluginBase


class GreeterPlugin(PluginBase):
    name = "greeter"

    def on_load(self, container, events) -> None:
        registry = container.resolve(CapabilityRegistry)
        registry.register(
            "greet",
            self._handle_greet,
            patterns=[r"\bhello\b", r"\bhi\b"],
            plugin=self.name,
            description="Responds to greetings.",
        )

    def on_unload(self, container, events) -> None:
        registry = container.resolve(CapabilityRegistry)
        registry.unregister_all_for_plugin(self.name)

    def _handle_greet(self, context: CapabilityContext) -> CapabilityResult:
        return CapabilityResult(text=f"Hello! You said: {context.request.text}")


def test_plugin_capability_is_reachable_through_orchestrator() -> None:
    container = ServiceContainer()
    events = EventBus()
    registry = CapabilityRegistry()
    container.register_instance(CapabilityRegistry, registry)

    orchestrator = Orchestrator(
        events=events,
        capability_registry=registry,
        intent_recognizer=PatternIntentRecognizer(registry),
        session_store=SessionStore(),
        memory=NullMemoryPort(),
        automation=NullAutomationPort(),
        filesystem=LocalFilesystemService(FilesystemConfig(allowed_dirs=[])),
        cowork=NullCoworkClientPort(),
    )

    plugin = GreeterPlugin()
    plugin.on_load(container, events)

    response = orchestrator.handle(Request(text="hi there", session_id="s1"))

    assert response.handled is True
    assert response.text == "Hello! You said: hi there"
    assert response.intent_name == "greet"


def test_plugin_unload_removes_its_capability_from_routing() -> None:
    container = ServiceContainer()
    events = EventBus()
    registry = CapabilityRegistry()
    container.register_instance(CapabilityRegistry, registry)

    orchestrator = Orchestrator(
        events=events,
        capability_registry=registry,
        intent_recognizer=PatternIntentRecognizer(registry),
        session_store=SessionStore(),
        memory=NullMemoryPort(),
        automation=NullAutomationPort(),
        filesystem=LocalFilesystemService(FilesystemConfig(allowed_dirs=[])),
        cowork=NullCoworkClientPort(),
    )

    plugin = GreeterPlugin()
    plugin.on_load(container, events)
    plugin.on_unload(container, events)

    response = orchestrator.handle(Request(text="hi there", session_id="s1"))

    assert response.handled is False
