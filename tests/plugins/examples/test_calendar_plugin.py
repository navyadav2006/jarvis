from __future__ import annotations

from jarvis.core.exceptions import FilesystemOperationError
from jarvis.core.filesystem import FilesystemPort
from jarvis.orchestrator.capability_registry import CapabilityRegistry
from jarvis.plugins.examples.calendar_plugin import CalendarPlugin

from .conftest import make_container_and_events, make_context


class FakeFilesystem:
    def __init__(self) -> None:
        self.files: dict[str, str] = {}

    def read(self, path):
        if str(path) not in self.files:
            raise FilesystemOperationError("not found")
        return self.files[str(path)]

    def write(self, path, content, *, confirmed=False):
        self.files[str(path)] = content


def _build_plugin(filesystem) -> tuple[CalendarPlugin, object, object]:
    container, events = make_container_and_events()
    container.register_instance(FilesystemPort, filesystem)
    registry = CapabilityRegistry()
    container.register_instance(CapabilityRegistry, registry)
    plugin = CalendarPlugin()
    plugin.on_load(container, events)
    return plugin, container, events


def test_configure_overrides_default_path() -> None:
    plugin = CalendarPlugin()
    plugin.configure({"calendar_path": "custom/cal.txt"})
    assert plugin._path == "custom/cal.txt"


def test_schedule_event_appends_a_line() -> None:
    filesystem = FakeFilesystem()
    plugin, *_ = _build_plugin(filesystem)

    plugin._schedule_event(make_context(text="lunch with Sam at noon"))

    assert "lunch with Sam at noon" in filesystem.files["data/calendar.txt"]


def test_list_events_reports_empty_calendar() -> None:
    filesystem = FakeFilesystem()
    plugin, *_ = _build_plugin(filesystem)

    result = plugin._list_events(make_context())

    assert result.text == "Your calendar is empty."


def test_list_events_returns_scheduled_events() -> None:
    filesystem = FakeFilesystem()
    plugin, *_ = _build_plugin(filesystem)
    plugin._schedule_event(make_context(text="dentist appointment"))

    result = plugin._list_events(make_context())

    assert "dentist appointment" in result.text
