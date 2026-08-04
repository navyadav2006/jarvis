from __future__ import annotations

import pytest

from jarvis.core.container import ServiceContainer
from jarvis.core.exceptions import ServiceNotRegisteredError


def test_register_and_resolve_instance(container: ServiceContainer) -> None:
    container.register_instance("settings", {"a": 1})
    assert container.resolve("settings") == {"a": 1}


def test_resolve_unregistered_key_raises(container: ServiceContainer) -> None:
    with pytest.raises(ServiceNotRegisteredError):
        container.resolve("missing")


def test_singleton_factory_runs_once(container: ServiceContainer) -> None:
    calls = []

    def factory() -> object:
        calls.append(1)
        return object()

    container.register_factory("thing", factory, singleton=True)
    first = container.resolve("thing")
    second = container.resolve("thing")

    assert first is second
    assert len(calls) == 1


def test_non_singleton_factory_runs_every_time(container: ServiceContainer) -> None:
    calls = []

    def factory() -> object:
        calls.append(1)
        return object()

    container.register_factory("thing", factory, singleton=False)
    first = container.resolve("thing")
    second = container.resolve("thing")

    assert first is not second
    assert len(calls) == 2


def test_has_reflects_registration_state(container: ServiceContainer) -> None:
    assert container.has("x") is False
    container.register_instance("x", 1)
    assert container.has("x") is True


def test_keys_lists_every_registered_key(container: ServiceContainer) -> None:
    container.register_instance("instance-key", 1)
    container.register_factory("factory-key", lambda: object())
    assert set(container.keys()) == {"instance-key", "factory-key"}


def test_reregistering_an_instance_key_overwrites_it(
    container: ServiceContainer, caplog: pytest.LogCaptureFixture
) -> None:
    container.register_instance("x", 1)
    with caplog.at_level("WARNING"):
        container.register_instance("x", 2)
    assert container.resolve("x") == 2
    assert "Overwriting" in caplog.text


def test_reregistering_a_factory_key_overwrites_it(
    container: ServiceContainer, caplog: pytest.LogCaptureFixture
) -> None:
    container.register_factory("x", lambda: 1)
    with caplog.at_level("WARNING"):
        container.register_factory("x", lambda: 2)
    assert container.resolve("x") == 2
    assert "Overwriting" in caplog.text
