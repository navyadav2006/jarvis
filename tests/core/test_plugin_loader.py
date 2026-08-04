from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core.container import ServiceContainer
from jarvis.core.events import EventBus
from jarvis.core.plugin_loader import PluginLoader

SAMPLE_PLUGIN_SOURCE = '''
from jarvis.plugins.base import PluginBase


class SamplePlugin(PluginBase):
    name = "sample"
    version = "0.0.1"

    def on_load(self, container, events):
        self.loaded = True
        events.subscribe("test.ping", self._on_ping)

    def on_unload(self, container, events):
        self.loaded = False

    def _on_ping(self, event):
        pass
'''

BROKEN_PLUGIN_SOURCE = '''
from jarvis.plugins.base import PluginBase


class BrokenPlugin(PluginBase):
    name = "broken"

    def on_load(self, container, events):
        raise RuntimeError("intentional failure")
'''


@pytest.fixture
def external_plugin_dir(tmp_path: Path) -> Path:
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    (plugin_dir / "sample_plugin.py").write_text(SAMPLE_PLUGIN_SOURCE, encoding="utf-8")
    return plugin_dir


def test_discovers_external_plugin(
    container: ServiceContainer, event_bus: EventBus, external_plugin_dir: Path
) -> None:
    loader = PluginLoader(container, event_bus, external_dir=external_plugin_dir)
    classes = loader.discover()
    names = {cls.name for cls in classes}
    assert "sample" in names


def test_load_all_activates_plugin(
    container: ServiceContainer, event_bus: EventBus, external_plugin_dir: Path
) -> None:
    loader = PluginLoader(container, event_bus, external_dir=external_plugin_dir)
    active = loader.load_all()

    assert "sample" in active
    assert active["sample"].loaded is True


def test_disabled_list_prevents_load(
    container: ServiceContainer, event_bus: EventBus, external_plugin_dir: Path
) -> None:
    loader = PluginLoader(
        container, event_bus, disabled=["sample"], external_dir=external_plugin_dir
    )
    active = loader.load_all()
    assert "sample" not in active


def test_enabled_allowlist_restricts_load(
    container: ServiceContainer, event_bus: EventBus, external_plugin_dir: Path
) -> None:
    (external_plugin_dir / "other_plugin.py").write_text(
        SAMPLE_PLUGIN_SOURCE.replace("sample", "other").replace("SamplePlugin", "OtherPlugin"),
        encoding="utf-8",
    )
    loader = PluginLoader(
        container, event_bus, enabled=["sample"], external_dir=external_plugin_dir
    )
    active = loader.load_all()
    assert set(active.keys()) == {"sample"}


def test_unload_calls_on_unload(
    container: ServiceContainer, event_bus: EventBus, external_plugin_dir: Path
) -> None:
    loader = PluginLoader(container, event_bus, external_dir=external_plugin_dir)
    loader.load_all()
    plugin = loader.active["sample"]

    loader.unload("sample")

    assert plugin.loaded is False
    assert "sample" not in loader.active


def test_missing_external_dir_does_not_raise(
    container: ServiceContainer, event_bus: EventBus, tmp_path: Path
) -> None:
    loader = PluginLoader(container, event_bus, external_dir=tmp_path / "does_not_exist")
    assert loader.load_all() == {}


def test_broken_plugin_raises_plugin_load_error(
    container: ServiceContainer, event_bus: EventBus, tmp_path: Path
) -> None:
    from jarvis.core.exceptions import PluginLoadError

    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    (plugin_dir / "broken_plugin.py").write_text(BROKEN_PLUGIN_SOURCE, encoding="utf-8")

    loader = PluginLoader(container, event_bus, external_dir=plugin_dir)
    with pytest.raises(PluginLoadError):
        loader.load_all()


def test_module_that_fails_to_import_is_skipped_not_fatal(
    container: ServiceContainer, event_bus: EventBus, external_plugin_dir: Path
) -> None:
    # A syntax error (or any import-time exception) in one external
    # module must not prevent discover()/load_all() from picking up
    # the other, valid modules in the same directory.
    (external_plugin_dir / "unparseable_plugin.py").write_text(
        "this is not valid python (((", encoding="utf-8"
    )
    loader = PluginLoader(container, event_bus, external_dir=external_plugin_dir)
    classes = loader.discover()
    assert {cls.name for cls in classes} == {"sample"}


# -- Phase 18: permissions, dependencies, configuration, versioning, install, catalog --

from jarvis.core.config.permissions_config import PermissionRule, PermissionsConfig  # noqa: E402
from jarvis.core.config.plugins_config import PluginEntryConfig  # noqa: E402
from jarvis.core.plugin_loader import PluginState, _dependency_order  # noqa: E402
from jarvis.orchestrator.capability_registry import CapabilityRegistry  # noqa: E402
from jarvis.plugins.base import PluginBase  # noqa: E402


class _Base(PluginBase):
    name = "base_service"
    version = "2.0.0"

    def on_load(self, container, events) -> None:
        pass


class _Dependent(PluginBase):
    name = "dependent_service"
    dependencies = ["base_service>=1.5.0"]

    def on_load(self, container, events) -> None:
        pass


class _TooStrictDependent(PluginBase):
    name = "too_strict"
    dependencies = ["base_service>=9.9.9"]

    def on_load(self, container, events) -> None:
        pass


class _MissingDependency(PluginBase):
    name = "orphan"
    dependencies = ["nonexistent_service"]

    def on_load(self, container, events) -> None:
        pass


class _NeedsPermission(PluginBase):
    name = "needs_permission"
    required_permissions = ["some.scope"]

    def on_load(self, container, events) -> None:
        pass


class _Configurable(PluginBase):
    name = "configurable"

    def configure(self, config: dict) -> None:
        self.greeting = config.get("greeting", "default")

    def on_load(self, container, events) -> None:
        pass


def test_dependency_order_loads_dependency_before_dependent() -> None:
    order = _dependency_order([_Dependent, _Base])
    assert [c.name for c in order] == ["base_service", "dependent_service"]


class _CycleA(PluginBase):
    name = "cycle_a"
    dependencies = ["cycle_b"]

    def on_load(self, container, events) -> None:
        pass


class _CycleB(PluginBase):
    name = "cycle_b"
    dependencies = ["cycle_a"]

    def on_load(self, container, events) -> None:
        pass


def test_dependency_order_falls_back_to_declared_order_on_a_cycle_within_the_batch() -> None:
    # A cycle among the classes being ordered together has no valid
    # topological order; _dependency_order() doesn't raise for it
    # (that's _check_dependencies's job per-plugin, at load time) --
    # it just returns them in declared order so load_all() can proceed
    # and let each one fail individually with a clear error.
    order = _dependency_order([_CycleA, _CycleB])
    assert {c.name for c in order} == {"cycle_a", "cycle_b"}


def test_satisfied_version_dependency_loads(
    container: ServiceContainer, event_bus: EventBus
) -> None:
    loader = PluginLoader(container, event_bus)
    by_name = {"base_service": _Base, "dependent_service": _Dependent}
    loader._load_one(_Base, by_name)
    loader._load_one(_Dependent, by_name)

    assert set(loader.active) == {"base_service", "dependent_service"}


def test_unsatisfied_version_dependency_is_skipped_not_fatal(
    container: ServiceContainer, event_bus: EventBus
) -> None:
    loader = PluginLoader(container, event_bus)
    by_name = {"base_service": _Base, "too_strict": _TooStrictDependent}
    loader._load_one(_Base, by_name)
    loader._load_one(_TooStrictDependent, by_name)

    assert "too_strict" not in loader.active
    assert loader.state_of("too_strict") == PluginState.FAILED


def test_missing_dependency_is_skipped_not_fatal(
    container: ServiceContainer, event_bus: EventBus
) -> None:
    loader = PluginLoader(container, event_bus)
    loader._load_one(_MissingDependency, {})
    assert "orphan" not in loader.active


def test_permission_denied_prevents_load(container: ServiceContainer, event_bus: EventBus) -> None:
    permissions = PermissionsConfig(default_policy="deny", rules=[])
    loader = PluginLoader(container, event_bus, permissions=permissions)
    loader._load_one(_NeedsPermission, {})
    assert "needs_permission" not in loader.active
    assert loader.state_of("needs_permission") == PluginState.FAILED


def test_permission_granted_allows_load(container: ServiceContainer, event_bus: EventBus) -> None:
    permissions = PermissionsConfig(
        default_policy="deny",
        rules=[PermissionRule(plugin="needs_permission", allow=["some.scope"])],
    )
    loader = PluginLoader(container, event_bus, permissions=permissions)
    loader._load_one(_NeedsPermission, {})
    assert "needs_permission" in loader.active


def test_no_permissions_config_skips_permission_check(
    container: ServiceContainer, event_bus: EventBus
) -> None:
    loader = PluginLoader(container, event_bus)  # permissions=None
    loader._load_one(_NeedsPermission, {})
    assert "needs_permission" in loader.active


def test_configure_receives_plugins_yaml_config(
    container: ServiceContainer, event_bus: EventBus
) -> None:
    loader = PluginLoader(
        container,
        event_bus,
        plugin_configs={"configurable": PluginEntryConfig(config={"greeting": "hi"})},
    )
    loader._load_one(_Configurable, {})
    assert loader.active["configurable"].greeting == "hi"


def test_configure_defaults_to_empty_dict_when_unconfigured(
    container: ServiceContainer, event_bus: EventBus
) -> None:
    loader = PluginLoader(container, event_bus)
    loader._load_one(_Configurable, {})
    assert loader.active["configurable"].greeting == "default"


def test_install_plugin_copies_file(
    container: ServiceContainer, event_bus: EventBus, tmp_path: Path
) -> None:
    source = tmp_path / "source" / "my_plugin.py"
    source.parent.mkdir()
    source.write_text("# a plugin")
    target_dir = tmp_path / "installed"

    loader = PluginLoader(container, event_bus, external_dir=target_dir)
    installed = loader.install_plugin(source, target_dir=target_dir)

    assert installed == target_dir / "my_plugin.py"
    assert installed.read_text() == "# a plugin"


def test_install_plugin_without_target_raises(
    container: ServiceContainer, event_bus: EventBus, tmp_path: Path
) -> None:
    from jarvis.core.exceptions import PluginLoadError

    loader = PluginLoader(container, event_bus)  # no external_dir
    with pytest.raises(PluginLoadError):
        loader.install_plugin(tmp_path / "x.py")


def test_plugin_catalog_lists_active_plugins_and_capabilities(
    container: ServiceContainer, event_bus: EventBus
) -> None:
    registry = CapabilityRegistry()
    registry.register("do_thing", lambda ctx: None, patterns=[r"x"], plugin="configurable")
    loader = PluginLoader(container, event_bus, capability_registry=registry)
    loader._load_one(_Configurable, {})

    catalog = loader.plugin_catalog()

    assert catalog == [
        {
            "name": "configurable",
            "version": "0.1.0",
            "description": "",
            "capabilities": ["do_thing"],
        }
    ]


def test_plugin_catalog_empty_without_capability_registry(
    container: ServiceContainer, event_bus: EventBus
) -> None:
    loader = PluginLoader(container, event_bus)
    loader._load_one(_Configurable, {})
    assert loader.plugin_catalog()[0]["capabilities"] == []
