from __future__ import annotations

from jarvis.core.cowork.models import CoworkTaskResponse
from jarvis.core.cowork.ports import NullCoworkClientPort
from jarvis.core.events import Event, EventBus
from jarvis.orchestrator.capability_registry import CapabilityRegistry
from jarvis.orchestrator.intent_recognizer import PatternIntentRecognizer
from jarvis.orchestrator.models import CapabilityContext, CapabilityResult, Request
from jarvis.orchestrator.orchestrator import Orchestrator
from jarvis.orchestrator.ports import AutomationAction
from jarvis.orchestrator.session_store import SessionStore

from .conftest import FakeAutomationPort, FakeCoworkClient, FakeFilesystemPort, FakeMemoryPort


def _collect(event_bus: EventBus, name: str) -> list[Event]:
    received: list[Event] = []
    event_bus.subscribe(name, received.append)
    return received


def _orchestrator_with_cowork(
    cowork, capability_registry: CapabilityRegistry, events: EventBus, *, plugin_catalog=None
) -> tuple[Orchestrator, FakeAutomationPort]:
    automation = FakeAutomationPort()
    orchestrator = Orchestrator(
        events=events,
        capability_registry=capability_registry,
        intent_recognizer=PatternIntentRecognizer(capability_registry),
        session_store=SessionStore(),
        memory=FakeMemoryPort(),
        automation=automation,
        filesystem=FakeFilesystemPort(),
        cowork=cowork,
        plugin_catalog=plugin_catalog,
    )
    return orchestrator, automation


def test_unmatched_request_with_no_cowork_backend_stays_unhandled(
    capability_registry: CapabilityRegistry, event_bus: EventBus
) -> None:
    orchestrator, _ = _orchestrator_with_cowork(
        NullCoworkClientPort(), capability_registry, event_bus
    )
    response = orchestrator.handle(Request(text="do something exotic", session_id="s1"))
    assert response.handled is False


def test_unmatched_request_routes_to_cowork_and_executes_plan_locally(
    capability_registry: CapabilityRegistry, event_bus: EventBus
) -> None:
    cowork_response = CoworkTaskResponse(
        task_id="t1",
        summary="clicked the button",
        steps=[
            {
                "step_id": 1,
                "description": "click",
                "action_type": "automation",
                "automation": {"name": "click", "parameters": {"x": 1}},
            }
        ],
    )
    cowork = FakeCoworkClient(response=cowork_response)
    orchestrator, automation = _orchestrator_with_cowork(cowork, capability_registry, event_bus)

    response = orchestrator.handle(Request(text="click the thing", session_id="s1"))

    assert response.handled is True
    assert response.text == "clicked the button"
    assert len(automation.executed) == 1
    assert automation.executed[0] == AutomationAction(name="click", parameters={"x": 1})
    assert len(cowork.submitted) == 1


def test_cowork_respond_step_produces_output_without_an_automation_call(
    capability_registry: CapabilityRegistry, event_bus: EventBus
) -> None:
    cowork_response = CoworkTaskResponse(
        task_id="t1",
        summary="answered",
        steps=[
            {
                "step_id": 1,
                "description": "answer a question",
                "action_type": "respond",
                "response_text": "the answer is 42",
            }
        ],
    )
    cowork = FakeCoworkClient(response=cowork_response)
    orchestrator, automation = _orchestrator_with_cowork(cowork, capability_registry, event_bus)

    response = orchestrator.handle(Request(text="what is the answer", session_id="s1"))

    assert response.handled is True
    assert automation.executed == []  # a respond step never touches AutomationPort
    assert response.data["steps"] == [
        {"step_id": 1, "success": True, "output": "the answer is 42"}
    ]


def test_cowork_with_empty_plan_falls_back_to_unhandled(
    capability_registry: CapabilityRegistry, event_bus: EventBus
) -> None:
    cowork = FakeCoworkClient(
        response=CoworkTaskResponse(task_id="t1", summary="nothing to do", steps=[])
    )
    orchestrator, automation = _orchestrator_with_cowork(cowork, capability_registry, event_bus)

    response = orchestrator.handle(Request(text="???", session_id="s1"))

    assert response.handled is False
    assert automation.executed == []


def test_cowork_failure_is_caught_and_falls_back_to_unhandled(
    capability_registry: CapabilityRegistry, event_bus: EventBus
) -> None:
    cowork = FakeCoworkClient(raises=RuntimeError("cowork is down"))
    events = _collect(event_bus, "cowork.error")
    orchestrator, _ = _orchestrator_with_cowork(cowork, capability_registry, event_bus)

    response = orchestrator.handle(Request(text="???", session_id="s1"))

    assert response.handled is False
    assert len(events) == 1


def test_registered_capability_is_tried_before_cowork(
    capability_registry: CapabilityRegistry, event_bus: EventBus
) -> None:
    def handler(context: CapabilityContext) -> CapabilityResult:
        return CapabilityResult(text="handled locally")

    capability_registry.register("greet", handler, patterns=[r"\bhello\b"], plugin="greeter")
    cowork = FakeCoworkClient(response=CoworkTaskResponse(task_id="t1", summary="unused"))
    orchestrator, _ = _orchestrator_with_cowork(cowork, capability_registry, event_bus)

    response = orchestrator.handle(Request(text="hello", session_id="s1"))

    assert response.text == "handled locally"
    assert cowork.submitted == []  # never consulted — a local capability already matched


def test_unmatched_request_returns_unhandled_response(orchestrator: Orchestrator) -> None:
    response = orchestrator.handle(Request(text="asdkjhaskjdh", session_id="s1"))
    assert response.handled is False
    assert response.text is None
    assert response.intent_name == "unknown"


def test_unmatched_request_publishes_unhandled_event(
    orchestrator: Orchestrator, event_bus: EventBus
) -> None:
    events = _collect(event_bus, "intent.unhandled")
    orchestrator.handle(Request(text="asdkjhaskjdh", session_id="s1"))
    assert len(events) == 1
    assert events[0].payload["session_id"] == "s1"


def test_registered_capability_is_invoked(
    orchestrator: Orchestrator, capability_registry: CapabilityRegistry
) -> None:
    def handler(context: CapabilityContext) -> CapabilityResult:
        return CapabilityResult(text="hi there", data={"foo": "bar"})

    capability_registry.register("greet", handler, patterns=[r"\bhello\b"], plugin="greeter")

    response = orchestrator.handle(Request(text="hello", session_id="s1"))

    assert response.handled is True
    assert response.text == "hi there"
    assert response.data == {"foo": "bar"}
    assert response.intent_name == "greet"


def test_capability_state_updates_persist_on_session(
    orchestrator: Orchestrator, capability_registry: CapabilityRegistry, session_store
) -> None:
    def handler(context: CapabilityContext) -> CapabilityResult:
        return CapabilityResult(text="ok", state_updates={"last_greeted": True})

    capability_registry.register("greet", handler, patterns=[r"\bhello\b"], plugin="greeter")
    orchestrator.handle(Request(text="hello", session_id="s1"))

    assert session_store.get("s1").context["last_greeted"] is True


def test_capability_handler_exception_is_isolated(
    orchestrator: Orchestrator, capability_registry: CapabilityRegistry, event_bus: EventBus
) -> None:
    def broken_handler(context: CapabilityContext) -> CapabilityResult:
        raise RuntimeError("plugin bug")

    capability_registry.register("broken", broken_handler, patterns=[r"\bbreak\b"], plugin="buggy")
    error_events = _collect(event_bus, "capability.error")

    response = orchestrator.handle(Request(text="break", session_id="s1"))

    assert response.handled is False
    assert response.text is None
    assert len(error_events) == 1
    assert error_events[0].payload["plugin"] == "buggy"


def test_memory_recall_is_passed_into_capability_context(
    orchestrator: Orchestrator, capability_registry: CapabilityRegistry, fake_memory: FakeMemoryPort
) -> None:
    from jarvis.orchestrator.ports import MemoryItem

    fake_memory.recall_response = [MemoryItem(content="user likes tea", score=0.9)]
    seen: list[CapabilityContext] = []

    def handler(context: CapabilityContext) -> CapabilityResult:
        seen.append(context)
        return CapabilityResult(text="ok")

    capability_registry.register("greet", handler, patterns=[r"\bhello\b"], plugin="greeter")
    orchestrator.handle(Request(text="hello", session_id="s1"))

    assert seen[0].recalled[0].content == "user likes tea"


def test_memory_remember_is_called_after_every_turn(
    orchestrator: Orchestrator, fake_memory: FakeMemoryPort
) -> None:
    orchestrator.handle(Request(text="anything", session_id="s1"))
    assert len(fake_memory.remembered) == 1
    session_id, turn = fake_memory.remembered[0]
    assert session_id == "s1"
    assert turn.request_text == "anything"


def test_memory_recall_failure_is_isolated_and_treated_as_empty(
    event_bus: EventBus,
    capability_registry: CapabilityRegistry,
    intent_recognizer: PatternIntentRecognizer,
    session_store: SessionStore,
    fake_automation: FakeAutomationPort,
    fake_filesystem: FakeFilesystemPort,
) -> None:
    # A broken memory backend must not take the whole request down —
    # recall() raising is caught and treated as "no memories found".
    orchestrator = Orchestrator(
        events=event_bus,
        capability_registry=capability_registry,
        intent_recognizer=intent_recognizer,
        session_store=session_store,
        memory=FakeMemoryPort(raises=RuntimeError("db is down")),
        automation=fake_automation,
        filesystem=fake_filesystem,
        cowork=NullCoworkClientPort(),
    )
    seen: list[CapabilityContext] = []

    def handler(context: CapabilityContext) -> CapabilityResult:
        seen.append(context)
        return CapabilityResult(text="ok")

    capability_registry.register("greet", handler, patterns=[r"\bhello\b"], plugin="greeter")
    response = orchestrator.handle(Request(text="hello", session_id="s1"))

    assert response.handled is True
    assert seen[0].recalled == []


def test_memory_remember_failure_does_not_break_the_response(
    event_bus: EventBus,
    capability_registry: CapabilityRegistry,
    intent_recognizer: PatternIntentRecognizer,
    session_store: SessionStore,
    fake_automation: FakeAutomationPort,
    fake_filesystem: FakeFilesystemPort,
) -> None:
    orchestrator = Orchestrator(
        events=event_bus,
        capability_registry=capability_registry,
        intent_recognizer=intent_recognizer,
        session_store=session_store,
        memory=FakeMemoryPort(raises=RuntimeError("db is down")),
        automation=fake_automation,
        filesystem=fake_filesystem,
        cowork=NullCoworkClientPort(),
    )
    response = orchestrator.handle(Request(text="anything", session_id="s1"))
    assert response.handled is False  # unmatched, but the call still completed normally


def test_capability_handler_can_use_automation_port(
    orchestrator: Orchestrator,
    capability_registry: CapabilityRegistry,
    fake_automation: FakeAutomationPort,
) -> None:
    def handler(context: CapabilityContext) -> CapabilityResult:
        result = context.automation.execute(AutomationAction(name="click", parameters={"x": 1}))
        return CapabilityResult(text="clicked" if result.success else "failed")

    capability_registry.register("click", handler, patterns=[r"\bclick\b"], plugin="clicker")
    response = orchestrator.handle(Request(text="click it", session_id="s1"))

    assert response.text == "clicked"
    assert len(fake_automation.executed) == 1


def test_session_history_accumulates_across_calls(
    orchestrator: Orchestrator, session_store
) -> None:
    orchestrator.handle(Request(text="first", session_id="s1"))
    orchestrator.handle(Request(text="second", session_id="s1"))

    session = session_store.get("s1")
    assert [t.request_text for t in session.history] == ["first", "second"]


def test_full_event_sequence_for_handled_request(
    orchestrator: Orchestrator, capability_registry: CapabilityRegistry, event_bus: EventBus
) -> None:
    def handler(context: CapabilityContext) -> CapabilityResult:
        return CapabilityResult(text="ok")

    capability_registry.register("greet", handler, patterns=[r"\bhello\b"], plugin="greeter")

    seen_events: list[str] = []
    for name in ("request.received", "intent.recognized", "request.completed"):
        event_bus.subscribe(name, lambda e, n=name: seen_events.append(n))

    orchestrator.handle(Request(text="hello", session_id="s1"))

    assert seen_events == ["request.received", "intent.recognized", "request.completed"]


def test_plugin_catalog_is_included_in_cowork_request_metadata(
    capability_registry: CapabilityRegistry, event_bus: EventBus
) -> None:
    catalog = [{"name": "github", "version": "1.0.0", "description": "x", "capabilities": []}]
    cowork = FakeCoworkClient(response=CoworkTaskResponse(task_id="t1", summary="unused"))
    orchestrator, _ = _orchestrator_with_cowork(
        cowork, capability_registry, event_bus, plugin_catalog=lambda: catalog
    )

    orchestrator.handle(Request(text="???", session_id="s1"))

    assert cowork.submitted[0].metadata["available_plugins"] == catalog


def test_no_plugin_catalog_omits_available_plugins_key(
    capability_registry: CapabilityRegistry, event_bus: EventBus
) -> None:
    cowork = FakeCoworkClient(response=CoworkTaskResponse(task_id="t1", summary="unused"))
    orchestrator, _ = _orchestrator_with_cowork(cowork, capability_registry, event_bus)

    orchestrator.handle(Request(text="???", session_id="s1"))

    assert "available_plugins" not in cowork.submitted[0].metadata
