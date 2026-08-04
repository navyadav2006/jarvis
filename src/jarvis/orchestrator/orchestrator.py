"""The central assistant orchestrator.

Orchestrator.handle() is the one request-handling pipeline for all of
Jarvis, regardless of whether the request came from the HTTP API, a
future CLI, or a future voice loop. Every collaborator it needs
(EventBus, CapabilityRegistry, IntentRecognizer, SessionStore,
MemoryPort, AutomationPort, FilesystemPort, CoworkClientPort, and an
optional `plugin_catalog` callable — Phase 18's
`PluginLoader.plugin_catalog`) is passed into `__init__`
rather than imported or constructed internally — this is the
dependency injection called for in this phase's requirements:
main.bootstrap() is the only place that decides *which* concrete
IntentRecognizer or MemoryPort to use, so swapping any of them (e.g. a
real memory backend for NullMemoryPort) never requires touching this
file.

Pipeline for every request:

    1. Look up (or create) the session's short-lived state.
    2. Publish "request.received" (observability — plugins/logging
       can react without the orchestrator knowing who's listening).
    3. Ask MemoryPort to recall anything relevant to this request.
    4. Ask IntentRecognizer what the request means.
    5. Ask CapabilityRegistry which plugin handles that intent.
       - No match: offer the request to Cowork for planning (Phase 9's
         `_try_cowork`) before giving up. Cowork returns a structured,
         inert plan (core/cowork/models.py's CoworkTaskResponse) — this
         method is what actually executes each step, via AutomationPort,
         the same as any other capability handler would. If Cowork has
         nothing to add either, publish "intent.unhandled" and return an
         unhandled Response — a normal, expected outcome, not an error.
       - Match: build a CapabilityContext (the plugin's only window
         into memory/automation/filesystem/session) and call the handler.
         A handler that raises is caught, logged, and reported via
         "capability.error" — one broken plugin must never crash the
         orchestrator or take down the request-handling loop.
    6. Record the turn in session history and hand it to MemoryPort
       to persist for long-term recall.
    7. Publish "request.completed" and return the Response.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from jarvis.core.cowork.models import CoworkTaskRequest
from jarvis.core.cowork.ports import CoworkClientPort
from jarvis.core.events import EventBus
from jarvis.core.filesystem import FilesystemPort
from jarvis.orchestrator.capability_registry import CapabilityRegistry
from jarvis.orchestrator.models import CapabilityContext, Intent, Request, Response, Turn
from jarvis.orchestrator.ports import (
    AutomationAction,
    AutomationPort,
    IntentRecognizer,
    MemoryItem,
    MemoryPort,
)
from jarvis.orchestrator.session_store import SessionStore

logger = logging.getLogger(__name__)

UNKNOWN_INTENT = "unknown"


class Orchestrator:
    def __init__(
        self,
        *,
        events: EventBus,
        capability_registry: CapabilityRegistry,
        intent_recognizer: IntentRecognizer,
        session_store: SessionStore,
        memory: MemoryPort,
        automation: AutomationPort,
        filesystem: FilesystemPort,
        cowork: CoworkClientPort,
        plugin_catalog: Callable[[], list[dict]] | None = None,
    ) -> None:
        self._events = events
        self._registry = capability_registry
        self._intent_recognizer = intent_recognizer
        self._sessions = session_store
        self._memory = memory
        self._automation = automation
        self._filesystem = filesystem
        self._cowork = cowork
        self._plugin_catalog = plugin_catalog

    def handle(self, request: Request) -> Response:
        session = self._sessions.get_or_create(request.session_id)

        self._events.publish(
            "request.received",
            {"session_id": request.session_id, "text": request.text, "source": request.source},
            source="orchestrator",
        )

        recalled = self._recall(request)
        intent = self._intent_recognizer.recognize(request.text, session)

        self._events.publish(
            "intent.recognized",
            {
                "session_id": request.session_id,
                "intent": intent.name,
                "confidence": intent.confidence,
            },
            source="orchestrator",
        )

        registration = self._registry.get(intent.name) if intent.name != UNKNOWN_INTENT else None

        if registration is None:
            handled, response_text, data = self._try_cowork(request, intent)
            if not handled:
                logger.info(
                    "No capability registered for intent %r (session=%s)",
                    intent.name,
                    request.session_id,
                )
                self._events.publish(
                    "intent.unhandled",
                    {"session_id": request.session_id, "text": request.text},
                    source="orchestrator",
                )
        else:
            context = CapabilityContext(
                request=request,
                intent=intent,
                session=session,
                memory=self._memory,
                automation=self._automation,
                filesystem=self._filesystem,
                recalled=recalled,
            )
            try:
                result = registration.handler(context)
                session.context.update(result.state_updates)
                handled, response_text, data = True, result.text, result.data
            except Exception:
                logger.exception(
                    "Capability %r (plugin=%r) raised while handling intent %r",
                    registration.name,
                    registration.plugin,
                    intent.name,
                )
                self._events.publish(
                    "capability.error",
                    {
                        "session_id": request.session_id,
                        "intent": intent.name,
                        "plugin": registration.plugin,
                    },
                    source="orchestrator",
                )
                handled, response_text, data = False, None, {}

        turn = Turn(
            request_text=request.text,
            response_text=response_text or "",
            intent_name=intent.name,
            timestamp=datetime.now(UTC),
        )
        session.add_turn(turn)
        self._remember(request, turn)

        self._events.publish(
            "request.completed",
            {"session_id": request.session_id, "intent": intent.name, "handled": handled},
            source="orchestrator",
        )

        return Response(
            session_id=request.session_id,
            intent_name=intent.name,
            handled=handled,
            text=response_text,
            data=data,
        )

    def _try_cowork(self, request: Request, intent: Intent) -> tuple[bool, str | None, dict]:
        """No local capability matched intent — offer the request to
        Cowork for planning. Cowork's response is inert data
        (CoworkTaskResponse/CoworkPlanStep — see core/cowork/models.py);
        every step here is *executed* by this method, via the same
        AutomationPort the orchestrator already depends on. Cowork
        itself never touches automation/filesystem/anything else.
        """
        metadata = {"source": request.source, "intent": intent.name}
        # "Expose plugin APIs to Claude Cowork" (Phase 18): if a
        # PluginLoader.plugin_catalog was supplied, every Cowork request
        # carries what Jarvis's active plugins can do — inert data,
        # never a way to call one directly (see plugin_loader.py's
        # module docstring for the full boundary explanation).
        if self._plugin_catalog is not None:
            metadata["available_plugins"] = self._plugin_catalog()
        cowork_request = CoworkTaskRequest(
            session_id=request.session_id,
            instruction=request.text,
            metadata=metadata,
        )
        try:
            response = self._cowork.submit(cowork_request)
        except Exception:
            logger.exception(
                "Cowork backend raised while submitting task (session=%s)", request.session_id
            )
            self._events.publish(
                "cowork.error", {"session_id": request.session_id}, source="orchestrator"
            )
            return False, None, {}

        if not response.steps:
            return False, None, {}

        self._events.publish(
            "cowork.routed",
            {
                "session_id": request.session_id,
                "task_id": response.task_id,
                "steps": len(response.steps),
            },
            source="orchestrator",
        )

        step_results: list[dict] = []
        for step in response.steps:
            if step.action_type == "automation" and step.automation is not None:
                action = AutomationAction(
                    name=step.automation.name, parameters=step.automation.parameters
                )
                result = self._automation.execute(action)
                step_results.append(
                    {
                        "step_id": step.step_id,
                        "success": result.success,
                        "output": result.output,
                        "error": result.error,
                    }
                )
            elif step.action_type == "respond":
                step_results.append(
                    {"step_id": step.step_id, "success": True, "output": step.response_text}
                )

        return True, response.summary, {"cowork_task_id": response.task_id, "steps": step_results}

    def _recall(self, request: Request) -> list[MemoryItem]:
        try:
            return self._memory.recall(request.session_id, request.text)
        except Exception:
            logger.exception(
                "Memory backend raised while recalling (session=%s)", request.session_id
            )
            return []

    def _remember(self, request: Request, turn: Turn) -> None:
        try:
            self._memory.remember(request.session_id, turn)
        except Exception:
            logger.exception(
                "Memory backend raised while remembering (session=%s)", request.session_id
            )
