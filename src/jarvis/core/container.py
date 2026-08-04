"""A minimal service container (dependency injection registry).

Jarvis is plugin-based: plugins should never import concrete services
from other plugins directly (that creates hard coupling and makes
plugins impossible to disable independently). Instead, every shared
service — settings, the event bus, later a database connection, a
vector index, etc. — is registered here by *key*, and plugins resolve
it at load time via ``container.resolve(key)``.

This is intentionally a plain registry, not a full DI framework
(no auto-wiring, no decorators, no constructor inspection). Jarvis's
service count is small and its plugin authors are the primary
audience; an explicit `register`/`resolve` API is easier to reason
about and debug than magic autowiring.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TypeVar

from jarvis.core.exceptions import ServiceNotRegisteredError

logger = logging.getLogger(__name__)

T = TypeVar("T")

_Factory = Callable[[], T]


class ServiceContainer:
    """Registry mapping a key (usually a type, sometimes a string) to a service."""

    def __init__(self) -> None:
        self._singletons: dict[object, object] = {}
        self._factories: dict[object, _Factory] = {}

    def register_instance(self, key: object, instance: object) -> None:
        """Register an already-constructed singleton (e.g. Settings, EventBus)."""
        if key in self._singletons or key in self._factories:
            logger.warning("Overwriting existing registration for key=%r", key)
        self._singletons[key] = instance
        logger.debug("Registered instance for key=%r (%s)", key, type(instance).__name__)

    def register_factory(self, key: object, factory: _Factory, *, singleton: bool = True) -> None:
        """Register a factory. If singleton=True, the factory runs at most once,
        the first time the key is resolved, and the result is cached.
        """
        if key in self._singletons or key in self._factories:
            logger.warning("Overwriting existing registration for key=%r", key)
        if singleton:
            self._factories[key] = _memoize(factory)
        else:
            self._factories[key] = factory
        logger.debug("Registered factory for key=%r (singleton=%s)", key, singleton)

    def resolve(self, key: object) -> object:
        if key in self._singletons:
            return self._singletons[key]
        if key in self._factories:
            return self._factories[key]()
        raise ServiceNotRegisteredError(f"No service registered for key={key!r}")

    def has(self, key: object) -> bool:
        return key in self._singletons or key in self._factories

    def keys(self) -> list[object]:
        return [*self._singletons.keys(), *self._factories.keys()]


def _memoize(factory: _Factory) -> _Factory:
    sentinel = object()
    cache: list[object] = [sentinel]

    def wrapper() -> object:
        if cache[0] is sentinel:
            cache[0] = factory()
        return cache[0]

    return wrapper
