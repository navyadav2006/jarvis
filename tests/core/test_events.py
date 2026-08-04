from __future__ import annotations

import asyncio

import pytest

from jarvis.core.events import Event, EventBus


def test_publish_calls_subscribed_handler(event_bus: EventBus) -> None:
    received = []
    event_bus.subscribe("thing.happened", lambda e: received.append(e))

    event_bus.publish("thing.happened", {"value": 42}, source="test")

    assert len(received) == 1
    event: Event = received[0]
    assert event.name == "thing.happened"
    assert event.payload == {"value": 42}
    assert event.source == "test"


def test_publish_with_no_subscribers_does_not_raise(event_bus: EventBus) -> None:
    event_bus.publish("nobody.listening")


def test_handler_exception_is_isolated(event_bus: EventBus) -> None:
    calls = []

    def broken(event: Event) -> None:
        raise RuntimeError("boom")

    def healthy(event: Event) -> None:
        calls.append(event)

    event_bus.subscribe("thing.happened", broken)
    event_bus.subscribe("thing.happened", healthy)

    event_bus.publish("thing.happened")

    assert len(calls) == 1


def test_unsubscribe_stops_future_delivery(event_bus: EventBus) -> None:
    received = []
    handler = lambda e: received.append(e)  # noqa: E731

    event_bus.subscribe("thing.happened", handler)
    event_bus.unsubscribe("thing.happened", handler)
    event_bus.publish("thing.happened")

    assert received == []


def test_publish_runs_async_handler(event_bus: EventBus) -> None:
    received = []

    async def handler(event: Event) -> None:
        received.append(event)

    event_bus.subscribe("thing.happened", handler)
    event_bus.publish("thing.happened")

    assert len(received) == 1


@pytest.mark.asyncio
async def test_publish_async_awaits_handler(event_bus: EventBus) -> None:
    received = []

    async def handler(event: Event) -> None:
        await asyncio.sleep(0)
        received.append(event)

    event_bus.subscribe("thing.happened", handler)
    await event_bus.publish_async("thing.happened")

    assert len(received) == 1


def test_unsubscribe_unregistered_handler_logs_a_warning_and_does_not_raise(
    event_bus: EventBus, caplog: pytest.LogCaptureFixture
) -> None:
    handler = lambda e: None  # noqa: E731
    with caplog.at_level("WARNING"):
        event_bus.unsubscribe("thing.happened", handler)  # was never subscribed
    assert "not registered" in caplog.text


@pytest.mark.asyncio
async def test_publish_async_isolates_a_raising_handler(event_bus: EventBus) -> None:
    calls = []

    async def broken(event: Event) -> None:
        raise RuntimeError("boom")

    async def healthy(event: Event) -> None:
        calls.append(event)

    event_bus.subscribe("thing.happened", broken)
    event_bus.subscribe("thing.happened", healthy)

    await event_bus.publish_async("thing.happened")

    assert len(calls) == 1
