"""CalendarPlugin: a reference example plugin (Phase 18) — a minimal,
real, dependency-free calendar backed by a single local text file
(`calendar.txt`, one event per line) via the existing `FilesystemPort`
(Phase 4). Not a real CalDAV/Google Calendar integration — those need
OAuth and a new dependency, out of scope for a framework example — but
genuinely functional for local-only scheduling.
"""

from __future__ import annotations

from datetime import UTC, datetime

from jarvis.core.container import ServiceContainer
from jarvis.core.events import EventBus
from jarvis.core.exceptions import FilesystemOperationError
from jarvis.core.filesystem import FilesystemPort
from jarvis.orchestrator.capability_registry import CapabilityRegistry
from jarvis.orchestrator.models import CapabilityContext, CapabilityResult
from jarvis.plugins.base import PluginBase

_CALENDAR_PATH = "data/calendar.txt"


class CalendarPlugin(PluginBase):
    name = "calendar"
    version = "1.0.0"
    description = "Schedule and list events in a local calendar file."
    required_permissions = ["filesystem.read", "filesystem.write"]

    def configure(self, config: dict) -> None:
        self._path = config.get("calendar_path", _CALENDAR_PATH)

    def on_load(self, container: ServiceContainer, events: EventBus) -> None:
        if not hasattr(self, "_path"):
            self._path = _CALENDAR_PATH
        self._filesystem: FilesystemPort = container.resolve(FilesystemPort)
        registry = container.resolve(CapabilityRegistry)
        registry.register(
            "calendar_schedule_event",
            self._schedule_event,
            patterns=[r"\bschedule\b", r"\badd (an )?event\b"],
            plugin=self.name,
            description="Add an event to the local calendar.",
        )
        registry.register(
            "calendar_list_events",
            self._list_events,
            patterns=[r"\bwhat's on my calendar\b", r"\blist events\b"],
            plugin=self.name,
            description="List upcoming events.",
        )

    def on_unload(self, container: ServiceContainer, events: EventBus) -> None:
        container.resolve(CapabilityRegistry).unregister_all_for_plugin(self.name)

    def _schedule_event(self, context: CapabilityContext) -> CapabilityResult:
        line = f"{datetime.now(UTC).isoformat()} | {context.request.text}\n"
        existing = self._read_existing()
        self._filesystem.write(self._path, existing + line, confirmed=True)
        return CapabilityResult(text="Event added to your calendar.")

    def _list_events(self, context: CapabilityContext) -> CapabilityResult:
        content = self._read_existing()
        if not content:
            return CapabilityResult(text="Your calendar is empty.")
        return CapabilityResult(text=content)

    def _read_existing(self) -> str:
        try:
            return self._filesystem.read(self._path)
        except FilesystemOperationError:
            return ""
