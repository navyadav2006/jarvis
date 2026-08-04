"""A synchronous, in-process publish/subscribe event bus.

Jarvis's architecture is event-driven: plugins should communicate by
publishing events ("wake word detected", "note saved", "transcription
ready") rather than calling each other's methods directly. That keeps
plugins independently loadable/unloadable — a plugin that publishes
an event doesn't need to know (or care) whether anything is listening.

Handlers run synchronously, in registration order, on the publisher's
call stack. This is a deliberate simplicity choice for Phase 1: no
background dispatch thread, no ordering surprises, no dropped events.
If a future phase needs non-blocking fan-out (e.g. a slow plugin
shouldn't stall the wake-word pipeline), that can be layered on top
via an async-aware subclass without changing this interface.

Both sync and async handlers are supported: async handlers are
scheduled with ``asyncio.run`` when publishing outside a running loop,
or awaited directly via ``publish_async`` from inside one.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

Handler = Callable[["Event"], None | Awaitable[None]]


@dataclass(frozen=True)
class Event:
    """Envelope for anything published on the bus."""

    name: str
    payload: dict[str, Any] = field(default_factory=dict)
    source: str | None = None


class EventBus:
    """In-process pub/sub. One instance is registered in the ServiceContainer
    and shared by every plugin.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, event_name: str, handler: Handler) -> None:
        self._handlers[event_name].append(handler)
        logger.debug("Subscribed %r to event %r", _handler_name(handler), event_name)

    def unsubscribe(self, event_name: str, handler: Handler) -> None:
        try:
            self._handlers[event_name].remove(handler)
        except ValueError:
            logger.warning(
                "Attempted to unsubscribe %r from %r but it was not registered",
                _handler_name(handler),
                event_name,
            )

    def publish(
        self, event_name: str, payload: dict[str, Any] | None = None, *, source: str | None = None
    ) -> None:
        """Fire-and-run all handlers for ``event_name`` synchronously.

        A handler that raises is logged and skipped — one broken
        plugin handler must never prevent the other subscribers of
        the same event from running.
        """
        event = Event(name=event_name, payload=payload or {}, source=source)
        handlers = list(self._handlers.get(event_name, ()))
        logger.debug("Publishing %r to %d handler(s)", event_name, len(handlers))

        for handler in handlers:
            try:
                result = handler(event)
                if inspect.isawaitable(result):
                    asyncio.run(result)
            except Exception:
                logger.exception(
                    "Handler %r raised while handling event %r", _handler_name(handler), event_name
                )

    async def publish_async(
        self, event_name: str, payload: dict[str, Any] | None = None, *, source: str | None = None
    ) -> None:
        """Same as publish(), but for use inside an already-running event loop
        (e.g. a FastAPI request handler) — awaits async handlers directly
        instead of spinning up a nested asyncio.run().
        """
        event = Event(name=event_name, payload=payload or {}, source=source)
        handlers = list(self._handlers.get(event_name, ()))
        logger.debug("Publishing (async) %r to %d handler(s)", event_name, len(handlers))

        for handler in handlers:
            try:
                result = handler(event)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                logger.exception(
                    "Handler %r raised while handling event %r", _handler_name(handler), event_name
                )


def _handler_name(handler: Handler) -> str:
    return getattr(handler, "__qualname__", repr(handler))
