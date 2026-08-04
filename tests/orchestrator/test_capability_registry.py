from __future__ import annotations

from jarvis.orchestrator.capability_registry import CapabilityRegistry
from jarvis.orchestrator.models import CapabilityContext, CapabilityResult


def _noop_handler(context: CapabilityContext) -> CapabilityResult:
    return CapabilityResult(text="ok")


def test_register_and_get(capability_registry: CapabilityRegistry) -> None:
    capability_registry.register(
        "greet", _noop_handler, patterns=[r"\bhello\b"], plugin="greeter"
    )
    registration = capability_registry.get("greet")
    assert registration is not None
    assert registration.plugin == "greeter"


def test_get_unknown_returns_none(capability_registry: CapabilityRegistry) -> None:
    assert capability_registry.get("nope") is None


def test_match_finds_registered_pattern(capability_registry: CapabilityRegistry) -> None:
    capability_registry.register("greet", _noop_handler, patterns=[r"\bhello\b"], plugin="greeter")
    result = capability_registry.match("well hello there")
    assert result is not None
    assert result.registration.name == "greet"


def test_match_is_case_insensitive(capability_registry: CapabilityRegistry) -> None:
    capability_registry.register("greet", _noop_handler, patterns=[r"\bhello\b"], plugin="greeter")
    assert capability_registry.match("HELLO") is not None


def test_match_no_registration_returns_none(capability_registry: CapabilityRegistry) -> None:
    assert capability_registry.match("anything") is None


def test_match_prefers_longer_match(capability_registry: CapabilityRegistry) -> None:
    capability_registry.register("generic", _noop_handler, patterns=[r"open"], plugin="a")
    capability_registry.register(
        "specific", _noop_handler, patterns=[r"open the browser"], plugin="b"
    )

    result = capability_registry.match("please open the browser now")
    assert result is not None
    assert result.registration.name == "specific"


def test_register_overwrites_existing_name(capability_registry: CapabilityRegistry) -> None:
    capability_registry.register("greet", _noop_handler, patterns=[r"hi"], plugin="a")
    capability_registry.register("greet", _noop_handler, patterns=[r"hi"], plugin="b")
    assert capability_registry.get("greet").plugin == "b"


def test_unregister_removes_capability(capability_registry: CapabilityRegistry) -> None:
    capability_registry.register("greet", _noop_handler, patterns=[r"hi"], plugin="a")
    capability_registry.unregister("greet")
    assert capability_registry.get("greet") is None


def test_unregister_unknown_is_a_noop(capability_registry: CapabilityRegistry) -> None:
    capability_registry.unregister("nope")  # must not raise


def test_unregister_all_for_plugin(capability_registry: CapabilityRegistry) -> None:
    capability_registry.register("a1", _noop_handler, patterns=[r"a1"], plugin="plugin_a")
    capability_registry.register("a2", _noop_handler, patterns=[r"a2"], plugin="plugin_a")
    capability_registry.register("b1", _noop_handler, patterns=[r"b1"], plugin="plugin_b")

    capability_registry.unregister_all_for_plugin("plugin_a")

    remaining = {reg.name for reg in capability_registry.all()}
    assert remaining == {"b1"}


def test_all_returns_every_registration(capability_registry: CapabilityRegistry) -> None:
    capability_registry.register("a", _noop_handler, patterns=[r"a"], plugin="p")
    capability_registry.register("b", _noop_handler, patterns=[r"b"], plugin="p")
    assert {reg.name for reg in capability_registry.all()} == {"a", "b"}
