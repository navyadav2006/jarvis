"""The contract every Jarvis plugin must implement.

A plugin is any class that subclasses PluginBase and is discoverable
by the plugin loader (see core/plugin_loader.py for the two discovery
mechanisms: built-in namespace package, or external directory).

Plugins receive the ServiceContainer and EventBus at load time and are
expected to do all of their setup — subscribing to events, registering
their own services — inside on_load(). They must clean up (unsubscribe,
release resources) inside on_unload(), since the loader supports
disabling plugins at runtime without restarting the process.

Phase 18 adds three class-level declarations beyond name/version —
`dependencies`, `required_permissions`, `description` — and one new
lifecycle hook, `configure()`. Together they're the plugin's manifest:
`PluginLoader` reads `dependencies`/`required_permissions` *before*
`on_load()` ever runs (to order loading and enforce permissions.yaml),
and calls `configure()` with the plugin's own `plugins.yaml` config
blob *before* `on_load()`, so a plugin's setup code can assume it's
already configured.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from jarvis.core.container import ServiceContainer
    from jarvis.core.events import EventBus


class PluginBase(ABC):
    """Base class for all Jarvis plugins.

    Attributes:
        name: Unique plugin identifier, used in config (plugins.enabled/
            disabled) and logging. Must be stable across versions.
        version: Dotted version string (e.g. "1.2.0") — compared
            against other plugins' `dependencies` constraints by
            core/plugin_loader.py's version_utils.py.
        description: One-line, human-readable summary — this is what
            `PluginLoader.plugin_catalog()` exposes to Claude Cowork.
        dependencies: Other plugin names this one requires, optionally
            with a version constraint (e.g. "docker>=1.0.0"). Checked,
            and used to order loading, before on_load() runs.
        required_permissions: Capability scopes (permissions.yaml)
            this plugin needs. Checked against
            `PermissionsConfig.is_allowed(name, scope)` before
            on_load() runs — a plugin missing a required grant is
            never loaded at all, not loaded-then-restricted.
    """

    name: str
    version: str = "0.1.0"
    description: str = ""
    dependencies: list[str] = []
    required_permissions: list[str] = []

    def __init__(self) -> None:
        if not getattr(self, "name", None):
            raise NotImplementedError(f"{type(self).__name__} must define a class-level `name`")

    def configure(self, config: dict[str, Any]) -> None:
        """Called once, before on_load(), with this plugin's config
        blob from plugins.yaml's `plugins.<name>.config` (empty dict if
        none was given). Default is a no-op; override to validate/store
        settings (API keys, connection strings, ...).
        """
        return None

    @abstractmethod
    def on_load(self, container: ServiceContainer, events: EventBus) -> None:
        """Called once when the plugin is activated (after configure()).
        Subscribe to events, register services/capabilities, and
        perform any setup here.
        """
        raise NotImplementedError

    def on_unload(self, container: ServiceContainer, events: EventBus) -> None:
        """Called when the plugin is deactivated. Default is a no-op;
        override to unsubscribe handlers or release resources.
        """
        return None
