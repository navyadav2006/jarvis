from __future__ import annotations

import pytest

from jarvis.plugins.base import PluginBase


def test_cannot_instantiate_plugin_base_directly() -> None:
    with pytest.raises(TypeError):
        PluginBase()  # type: ignore[abstract]


def test_subclass_without_name_raises() -> None:
    class Nameless(PluginBase):
        def on_load(self, container, events) -> None:
            pass

    with pytest.raises(NotImplementedError):
        Nameless()


def test_subclass_with_name_and_on_load_instantiates() -> None:
    class Valid(PluginBase):
        name = "valid"

        def on_load(self, container, events) -> None:
            pass

    plugin = Valid()
    assert plugin.name == "valid"
    assert plugin.version == "0.1.0"


def test_default_manifest_fields() -> None:
    class Valid(PluginBase):
        name = "valid"

        def on_load(self, container, events) -> None:
            pass

    plugin = Valid()
    assert plugin.description == ""
    assert plugin.dependencies == []
    assert plugin.required_permissions == []


def test_configure_defaults_to_a_noop() -> None:
    class Valid(PluginBase):
        name = "valid"

        def on_load(self, container, events) -> None:
            pass

    Valid().configure({"anything": "goes"})  # must not raise


def test_configure_can_be_overridden() -> None:
    class Configured(PluginBase):
        name = "configured"

        def configure(self, config: dict) -> None:
            self.value = config.get("value")

        def on_load(self, container, events) -> None:
            pass

    plugin = Configured()
    plugin.configure({"value": 42})
    assert plugin.value == 42
