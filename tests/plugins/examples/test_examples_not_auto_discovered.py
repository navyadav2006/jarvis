"""The six reference example plugins must never be picked up by
PluginLoader's built-in-namespace discovery by default — several of
them would run subprocess/network code in on_load() paths if they
were. See src/jarvis/plugins/examples/__init__.py's module docstring.
"""

from __future__ import annotations

from jarvis.core.container import ServiceContainer
from jarvis.core.events import EventBus
from jarvis.core.plugin_loader import PluginLoader

EXAMPLE_PLUGIN_NAMES = {
    "obsidian",
    "calendar",
    "email",
    "docker",
    "postgresql",
    "github",
}


def test_example_plugins_are_not_discovered_by_default() -> None:
    loader = PluginLoader(ServiceContainer(), EventBus())
    discovered_names = {cls.name for cls in loader.discover()}
    assert discovered_names.isdisjoint(EXAMPLE_PLUGIN_NAMES)
