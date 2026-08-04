"""Plugin discovery, installation, configuration, permissions,
lifecycle management, versioning, and dependency resolution (Phase 18
completes what Phase 1 started).

Two discovery sources are scanned, in order:

1. Built-in plugins: submodules of the ``jarvis.plugins`` namespace
   package (shipped with Jarvis itself). Reference example plugins
   (GitHub/Docker/PostgreSQL/Obsidian/Calendar/Email) live under
   ``jarvis.plugins.examples`` — a subpackage, not re-exported from
   ``jarvis.plugins.examples.__init__`` — specifically so they are
   *not* auto-discovered/auto-loaded by default; add a plugin's module
   to ``plugins.yaml``'s `enabled` list (or copy it into the external
   plugins directory) to actually activate one.
2. External plugins: top-level Python packages/modules found in the
   directory configured by ``paths.plugins_dir`` (default ``./plugins``),
   so users can drop in third-party plugins without modifying the
   Jarvis source tree. ``install_plugin()`` is how one gets there.

Before a discovered plugin is instantiated, three checks run, in order
(any failure skips *only* that plugin — one broken/misconfigured plugin
must never prevent the rest from loading, the same "denial doesn't
crash the batch" principle Phase 15's ExecutionEngine and Phase 17's
PlanningEngine both follow):

1. **Dependency resolution** — `dependencies` (name, optionally
   version-constrained) must all be satisfied by another
   already-loaded-or-about-to-load plugin; a topological sort
   (Kahn's algorithm, same technique Phase 17's `topological_waves()`
   uses for task scheduling) decides load order so a dependency is
   always loaded before whatever needs it.
2. **Permission check** — every `required_permissions` scope must be
   granted by `permissions.yaml` (`PermissionsConfig.is_allowed`,
   modeled since Phase 3, enforced for automation/execution since
   Phase 15 — plugins are the second real caller).
3. **Configuration** — `configure(plugins.yaml's per-plugin config
   dict)` runs before `on_load()`.

``plugin_catalog()`` is "expose plugin APIs to Claude Cowork": a
JSON-safe description of every active plugin and the capabilities it
registered, meant to be included in a `CoworkTaskRequest`'s metadata
(see `orchestrator/orchestrator.py`'s `_try_cowork()`) so Cowork's
planning can reference what Jarvis is actually capable of — Jarvis
still executes every capability itself; Cowork only ever sees the
catalog, never a way to call one directly.
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import logging
import pkgutil
import shutil
from enum import StrEnum
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

from jarvis.core.container import ServiceContainer
from jarvis.core.events import EventBus
from jarvis.core.exceptions import (
    PluginContractError,
    PluginDependencyError,
    PluginLoadError,
    PluginPermissionError,
)
from jarvis.core.version_utils import parse_dependency, satisfies
from jarvis.plugins.base import PluginBase

if TYPE_CHECKING:
    from jarvis.core.config.permissions_config import PermissionsConfig
    from jarvis.core.config.plugins_config import PluginEntryConfig
    from jarvis.orchestrator.capability_registry import CapabilityRegistry

logger = logging.getLogger(__name__)

BUILTIN_NAMESPACE = "jarvis.plugins"


class PluginState(StrEnum):
    DISCOVERED = "discovered"
    LOADED = "loaded"
    FAILED = "failed"
    UNLOADED = "unloaded"


class PluginLoader:
    """Discovers, loads, and holds the registry of active plugins."""

    def __init__(
        self,
        container: ServiceContainer,
        events: EventBus,
        *,
        enabled: list[str] | None = None,
        disabled: list[str] | None = None,
        external_dir: Path | None = None,
        permissions: PermissionsConfig | None = None,
        plugin_configs: dict[str, PluginEntryConfig] | None = None,
        capability_registry: CapabilityRegistry | None = None,
    ) -> None:
        self._container = container
        self._events = events
        self._enabled = set(enabled or [])
        self._disabled = set(disabled or [])
        self._external_dir = external_dir
        self._permissions = permissions
        self._plugin_configs = plugin_configs or {}
        self._capability_registry = capability_registry
        self._active: dict[str, PluginBase] = {}
        self._states: dict[str, PluginState] = {}

    @property
    def active(self) -> dict[str, PluginBase]:
        return dict(self._active)

    def state_of(self, name: str) -> PluginState | None:
        return self._states.get(name)

    def discover(self) -> list[type[PluginBase]]:
        """Find every PluginBase subclass across built-in + external sources,
        without instantiating or loading any of them.
        """
        classes: list[type[PluginBase]] = []
        for module in self._iter_builtin_modules():
            classes.extend(_plugin_classes_in(module))
        if self._external_dir is not None:
            for module in self._iter_external_modules(self._external_dir):
                classes.extend(_plugin_classes_in(module))
        for plugin_cls in classes:
            self._states.setdefault(plugin_cls.name, PluginState.DISCOVERED)
        logger.info("Discovered %d plugin class(es)", len(classes))
        return classes

    def load_all(self) -> dict[str, PluginBase]:
        """Discover, filter by enabled/disabled, resolve dependency order,
        and load every plugin that passes every check. Returns the
        active registry.
        """
        candidates = [c for c in self.discover() if self._should_load(c.name)]
        by_name = {c.name: c for c in candidates}
        for plugin_cls in _dependency_order(candidates):
            self._load_one(plugin_cls, by_name)
        return self.active

    def unload_all(self) -> None:
        for name in list(self._active.keys()):
            self.unload(name)

    def unload(self, name: str) -> None:
        plugin = self._active.pop(name, None)
        if plugin is None:
            return
        try:
            plugin.on_unload(self._container, self._events)
            logger.info("Unloaded plugin %r", name)
        except Exception:
            logger.exception("Plugin %r raised during on_unload", name)
        self._states[name] = PluginState.UNLOADED

    def install_plugin(self, source: Path, *, target_dir: Path | None = None) -> Path:
        """Copy a plugin file or directory into the external plugins
        directory so the next discover()/load_all() picks it up —
        "Installation" for a local-first app: there is no registry to
        publish to, just a directory `discover()` already scans.
        """
        destination_dir = target_dir or self._external_dir
        if destination_dir is None:
            raise PluginLoadError("no external plugin directory configured to install into")
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / source.name
        if source.is_dir():
            shutil.copytree(source, destination, dirs_exist_ok=True)
        else:
            shutil.copy2(source, destination)
        logger.info("Installed plugin from %s to %s", source, destination)
        return destination

    def plugin_catalog(self) -> list[dict]:
        """"Expose plugin APIs to Claude Cowork" — one JSON-safe entry
        per active plugin, listing the capabilities it registered.
        Inert data, same as every other Cowork-facing structure since
        Phase 9: Cowork can read this, never call anything through it.
        """
        catalog = []
        for name, plugin in self._active.items():
            capabilities: list[str] = []
            if self._capability_registry is not None:
                capabilities = [
                    reg.name for reg in self._capability_registry.all() if reg.plugin == name
                ]
            catalog.append(
                {
                    "name": name,
                    "version": plugin.version,
                    "description": plugin.description,
                    "capabilities": capabilities,
                }
            )
        return catalog

    # -- internals -----------------------------------------------------------

    def _load_one(
        self, plugin_cls: type[PluginBase], candidates: dict[str, type[PluginBase]]
    ) -> None:
        name = getattr(plugin_cls, "name", None)
        if not name:
            raise PluginContractError(f"{plugin_cls.__name__} does not define `name`")

        try:
            self._check_dependencies(plugin_cls, candidates)
            self._check_permissions(plugin_cls)
            instance = plugin_cls()
            instance.configure(self._config_for(name))
            instance.on_load(self._container, self._events)
        except (PluginDependencyError, PluginPermissionError) as exc:
            logger.warning("Skipping plugin %r: %s", name, exc)
            self._states[name] = PluginState.FAILED
            return
        except Exception as exc:
            self._states[name] = PluginState.FAILED
            raise PluginLoadError(f"Failed to load plugin {name!r}: {exc}") from exc

        self._active[name] = instance
        self._states[name] = PluginState.LOADED
        logger.info("Loaded plugin %r (version=%s)", name, instance.version)

    def _check_dependencies(
        self, plugin_cls: type[PluginBase], candidates: dict[str, type[PluginBase]]
    ) -> None:
        for spec in plugin_cls.dependencies:
            dep_name, operator, required_version = parse_dependency(spec)
            # `version` is a class attribute (a default or an override),
            # so it's readable without instantiating — the dependency
            # doesn't need to be loaded yet for its version to be known,
            # only present among this batch's candidates or already active.
            dependency_version = (
                self._active[dep_name].version
                if dep_name in self._active
                else getattr(candidates.get(dep_name), "version", None)
            )
            if dependency_version is None:
                raise PluginDependencyError(
                    f"{plugin_cls.name!r} requires {dep_name!r}, which is not available"
                )
            if not satisfies(dependency_version, operator, required_version):
                raise PluginDependencyError(
                    f"{plugin_cls.name!r} requires {spec!r}, found {dep_name} "
                    f"{dependency_version}"
                )

    def _check_permissions(self, plugin_cls: type[PluginBase]) -> None:
        if self._permissions is None:
            return
        for scope in plugin_cls.required_permissions:
            if not self._permissions.is_allowed(plugin_cls.name, scope):
                raise PluginPermissionError(
                    f"{plugin_cls.name!r} requires permission scope {scope!r}, "
                    "which permissions.yaml does not grant"
                )

    def _config_for(self, name: str) -> dict:
        entry = self._plugin_configs.get(name)
        return dict(entry.config) if entry is not None else {}

    def _should_load(self, name: str) -> bool:
        if self._enabled:
            return name in self._enabled
        return name not in self._disabled

    def _iter_builtin_modules(self) -> list[ModuleType]:
        try:
            package = importlib.import_module(BUILTIN_NAMESPACE)
        except ImportError:
            logger.warning("Built-in plugin namespace %r not importable", BUILTIN_NAMESPACE)
            return []

        modules: list[ModuleType] = []
        if not hasattr(package, "__path__"):
            return modules

        for info in pkgutil.iter_modules(package.__path__, prefix=f"{BUILTIN_NAMESPACE}."):
            try:
                modules.append(importlib.import_module(info.name))
            except Exception:
                logger.exception("Failed to import built-in plugin module %r", info.name)
        return modules

    def _iter_external_modules(self, directory: Path) -> list[ModuleType]:
        modules: list[ModuleType] = []
        if not directory.is_dir():
            logger.debug("External plugin directory %s does not exist; skipping", directory)
            return modules

        for entry in sorted(directory.iterdir()):
            if entry.name.startswith((".", "_")):
                continue
            if entry.is_file() and entry.suffix == ".py":
                module_file, module_name = entry, entry.stem
            elif entry.is_dir() and (entry / "__init__.py").is_file():
                module_file, module_name = entry / "__init__.py", entry.name
            else:
                continue

            spec = importlib.util.spec_from_file_location(
                f"jarvis_external_plugins.{module_name}", module_file
            )
            if spec is None or spec.loader is None:
                logger.warning("Could not build import spec for %s", module_file)
                continue
            module = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(module)
                modules.append(module)
            except Exception:
                logger.exception("Failed to import external plugin module %s", module_file)
        return modules


def _plugin_classes_in(module: ModuleType) -> list[type[PluginBase]]:
    found = []
    for _, obj in inspect.getmembers(module, inspect.isclass):
        defined_here = obj.__module__ == module.__name__
        if issubclass(obj, PluginBase) and obj is not PluginBase and defined_here:
            found.append(obj)
    return found


def _dependency_order(classes: list[type[PluginBase]]) -> list[type[PluginBase]]:
    """Kahn's-algorithm ordering so a plugin's dependencies (among
    `classes` itself) load before it does. A dependency on a plugin
    NOT in `classes` (e.g. already active, or genuinely missing) is
    left for `_check_dependencies` to resolve/reject per-plugin — this
    function only orders what's being loaded in this batch.
    """
    by_name = {c.name: c for c in classes}
    remaining = {
        c.name: {parse_dependency(d)[0] for d in c.dependencies} & set(by_name) for c in classes
    }
    ordered: list[type[PluginBase]] = []
    while remaining:
        ready = sorted(name for name, deps in remaining.items() if not deps)
        if not ready:
            # Cyclic among this batch — fall back to declared order for
            # the rest; _check_dependencies will report the real error
            # for whichever ones can't actually resolve.
            ordered.extend(by_name[name] for name in remaining)
            break
        for name in ready:
            ordered.append(by_name[name])
            del remaining[name]
        for deps in remaining.values():
            deps.difference_update(ready)
    return ordered
