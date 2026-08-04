"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

from jarvis.core.container import ServiceContainer
from jarvis.core.events import EventBus


@pytest.fixture
def container() -> ServiceContainer:
    return ServiceContainer()


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()
