"""The plugin-driven routing table.

This is what makes "the orchestrator should not know implementation
details of plugins" actually true: a plugin calls
`registry.register(name, handler, patterns=[...], plugin=self.name)`
from its own `on_load()`, and the orchestrator only ever calls
`registry.get(name)` / `registry.match(text)`. The orchestrator never
imports a plugin class, never has a per-plugin if/elif chain, and does
not need to change when a plugin is added, removed, or replaced.

Thread-safe because plugins register at startup on the main thread but
FastAPI can serve concurrent requests that read the registry — a
`threading.Lock` guards every access rather than relying on incidental
dict-operation atomicity.
"""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass

from jarvis.orchestrator.models import CapabilityContext, CapabilityResult

logger = logging.getLogger(__name__)

CapabilityHandler = Callable[[CapabilityContext], CapabilityResult]


@dataclass
class CapabilityRegistration:
    name: str
    handler: CapabilityHandler
    patterns: list[re.Pattern[str]]
    plugin: str
    description: str = ""


@dataclass
class _MatchResult:
    registration: CapabilityRegistration
    match: re.Match[str]


class CapabilityRegistry:
    """Registry of intent-name -> handler, populated entirely by plugins."""

    def __init__(self) -> None:
        self._registrations: dict[str, CapabilityRegistration] = {}
        self._lock = threading.Lock()

    def register(
        self,
        name: str,
        handler: CapabilityHandler,
        *,
        patterns: list[str],
        plugin: str,
        description: str = "",
    ) -> None:
        """Register a capability. `patterns` are regex strings (case-insensitive)
        matched against raw request text by the default IntentRecognizer.
        """
        compiled = [re.compile(p, re.IGNORECASE) for p in patterns]
        registration = CapabilityRegistration(
            name=name, handler=handler, patterns=compiled, plugin=plugin, description=description
        )
        with self._lock:
            existing = self._registrations.get(name)
            if existing is not None:
                logger.warning(
                    "Capability %r already registered by plugin %r; overwriting with %r",
                    name,
                    existing.plugin,
                    plugin,
                )
            self._registrations[name] = registration
        logger.info(
            "Registered capability %r from plugin %r (%d pattern(s))", name, plugin, len(compiled)
        )

    def unregister(self, name: str) -> None:
        """Remove a capability. Plugins are expected to call this from their
        own on_unload() for everything they registered, mirroring how
        EventBus subscriptions are cleaned up.
        """
        with self._lock:
            removed = self._registrations.pop(name, None)
        if removed is not None:
            logger.info("Unregistered capability %r (plugin=%r)", name, removed.plugin)

    def unregister_all_for_plugin(self, plugin: str) -> None:
        """Convenience for on_unload(): drop every capability a given plugin
        registered, without it needing to remember each name individually.
        """
        with self._lock:
            to_remove = [name for name, reg in self._registrations.items() if reg.plugin == plugin]
            for name in to_remove:
                del self._registrations[name]
        if to_remove:
            logger.info("Unregistered %d capability(ies) for plugin %r", len(to_remove), plugin)

    def get(self, name: str) -> CapabilityRegistration | None:
        with self._lock:
            return self._registrations.get(name)

    def match(self, text: str) -> _MatchResult | None:
        """Find the best-matching registered capability for `text`.

        "Best" = the match with the longest matched substring, which
        favors more specific patterns over generic ones without
        requiring plugins to declare explicit priorities. Ties keep
        the first-registered capability.
        """
        with self._lock:
            registrations = list(self._registrations.values())

        best: _MatchResult | None = None
        best_score = -1
        for registration in registrations:
            for pattern in registration.patterns:
                found = pattern.search(text)
                if found is None:
                    continue
                score = found.end() - found.start()
                if score > best_score:
                    best_score = score
                    best = _MatchResult(registration=registration, match=found)
        return best

    def all(self) -> list[CapabilityRegistration]:
        with self._lock:
            return list(self._registrations.values())
