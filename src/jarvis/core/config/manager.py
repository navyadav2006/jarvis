"""ConfigManager: loads, validates, and (optionally) live-reloads all
twelve config domains as one unit.

Two deliberately different error-handling behaviors:

  - The *initial* load (inside `__init__`, i.e. at process startup)
    lets ConfigurationError propagate out of the constructor. An
    invalid config at startup should stop the process before it binds
    a port or loads a single plugin — failing loudly here is correct.
  - A *reload* (triggered by the file watcher, or called manually)
    catches ConfigurationError, logs it, publishes "config.reload_failed"
    on the EventBus, and keeps serving the last known-good config. A
    typo saved mid-edit to a running assistant's settings.yaml must not
    take it down — this is the "fail-safe at runtime" half of the
    error-handling requirement, deliberately asymmetric with startup.

Live reload itself is a polling thread comparing file mtimes, not a
filesystem-event watcher (no `watchdog` dependency) — mtime polling is
enough for config files that change a few times a session at most, and
keeps the dependency list matched to what Phase 3 actually needs.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jarvis.core.config._paths import DEFAULT_CONFIG_DIR
from jarvis.core.config.app_config import SETTINGS_FILENAME, Settings
from jarvis.core.config.cowork_config import COWORK_FILENAME, CoworkConfig
from jarvis.core.config.execution_config import EXECUTION_FILENAME, ExecutionConfig
from jarvis.core.config.filesystem_config import FILESYSTEM_FILENAME, FilesystemConfig
from jarvis.core.config.loader import env_overrides, load_typed_config
from jarvis.core.config.memory_config import MEMORY_FILENAME, MemoryConfig
from jarvis.core.config.permissions_config import PERMISSIONS_FILENAME, PermissionsConfig
from jarvis.core.config.planning_config import PLANNING_FILENAME, PlanningConfig
from jarvis.core.config.plugins_config import PLUGINS_FILENAME, PluginsConfig
from jarvis.core.config.security_config import SECURITY_FILENAME, SecurityConfig
from jarvis.core.config.vault_config import VAULT_FILENAME, VaultConfig
from jarvis.core.config.voice_config import VOICE_FILENAME, VoiceConfig
from jarvis.core.config.workflow_config import WORKFLOW_FILENAME, WorkflowConfig
from jarvis.core.events import EventBus
from jarvis.core.exceptions import ConfigurationError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LoadedConfig:
    """One consistent snapshot of every config domain, swapped in atomically
    by ConfigManager on every successful load/reload.
    """

    settings: Settings
    permissions: PermissionsConfig
    voice: VoiceConfig
    memory: MemoryConfig
    plugins: PluginsConfig
    filesystem: FilesystemConfig
    cowork: CoworkConfig
    vault: VaultConfig
    execution: ExecutionConfig
    planning: PlanningConfig
    security: SecurityConfig
    workflow: WorkflowConfig


class ConfigManager:
    def __init__(
        self, config_dir: Path = DEFAULT_CONFIG_DIR, events: EventBus | None = None
    ) -> None:
        self._config_dir = config_dir
        self._events = events
        self._lock = threading.RLock()
        self._current = self._load_all()
        self._mtimes = self._snapshot_mtimes()
        self._watch_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    # -- read API, always returns the current in-memory snapshot ----------

    @property
    def settings(self) -> Settings:
        with self._lock:
            return self._current.settings

    @property
    def permissions(self) -> PermissionsConfig:
        with self._lock:
            return self._current.permissions

    @property
    def voice(self) -> VoiceConfig:
        with self._lock:
            return self._current.voice

    @property
    def memory(self) -> MemoryConfig:
        with self._lock:
            return self._current.memory

    @property
    def plugins(self) -> PluginsConfig:
        with self._lock:
            return self._current.plugins

    @property
    def filesystem(self) -> FilesystemConfig:
        with self._lock:
            return self._current.filesystem

    @property
    def cowork(self) -> CoworkConfig:
        with self._lock:
            return self._current.cowork

    @property
    def vault(self) -> VaultConfig:
        with self._lock:
            return self._current.vault

    @property
    def execution(self) -> ExecutionConfig:
        with self._lock:
            return self._current.execution

    @property
    def planning(self) -> PlanningConfig:
        with self._lock:
            return self._current.planning

    @property
    def security(self) -> SecurityConfig:
        with self._lock:
            return self._current.security

    @property
    def workflow(self) -> WorkflowConfig:
        with self._lock:
            return self._current.workflow

    def snapshot(self) -> LoadedConfig:
        with self._lock:
            return self._current

    # -- reload -------------------------------------------------------------

    def attach_events(self, events: EventBus) -> None:
        """Wire in an EventBus after construction. Config loads before the
        EventBus exists in the startup sequence (see main.bootstrap()), so
        this can't just be a constructor-only parameter for the common case.
        """
        self._events = events

    def reload(self) -> bool:
        """Re-read and re-validate every config file. Returns True if the
        reload succeeded AND something actually changed, False if it
        failed (old config kept) or nothing changed.
        """
        try:
            new_config = self._load_all()
        except ConfigurationError as exc:
            logger.error("Configuration reload failed; keeping previous configuration:\n%s", exc)
            self._publish("config.reload_failed", {"error": str(exc)})
            return False

        with self._lock:
            changed = new_config != self._current
            self._current = new_config
            self._mtimes = self._snapshot_mtimes()

        if changed:
            logger.info("Configuration reloaded from %s", self._config_dir)
            self._publish("config.reloaded", {})
        else:
            logger.debug("Configuration reload: no changes detected")
        return changed

    # -- background file watching (live reload) ------------------------------

    def start_watching(self, poll_interval_seconds: float = 2.0) -> None:
        if self._watch_thread is not None:
            return
        self._stop_event.clear()
        self._watch_thread = threading.Thread(
            target=self._watch_loop,
            args=(poll_interval_seconds,),
            name="jarvis-config-watcher",
            daemon=True,
        )
        self._watch_thread.start()
        logger.info("Started config file watcher (poll_interval=%.1fs)", poll_interval_seconds)

    def stop_watching(self) -> None:
        if self._watch_thread is None:
            return
        self._stop_event.set()
        self._watch_thread.join(timeout=5)
        self._watch_thread = None
        logger.info("Stopped config file watcher")

    def _watch_loop(self, poll_interval_seconds: float) -> None:
        while not self._stop_event.wait(poll_interval_seconds):
            try:
                if self._changed_on_disk():
                    logger.info("Detected change in config files; reloading")
                    self.reload()
            except Exception:
                logger.exception("Unexpected error in config watcher loop")

    def _changed_on_disk(self) -> bool:
        return self._snapshot_mtimes() != self._mtimes

    # -- internals -----------------------------------------------------------

    def _snapshot_mtimes(self) -> dict[str, float]:
        result: dict[str, float] = {}
        for key, filename in self._files().items():
            path = self._config_dir / filename
            if path.exists():
                result[key] = path.stat().st_mtime
        return result

    def _files(self) -> dict[str, str]:
        return {
            "settings": SETTINGS_FILENAME,
            "permissions": PERMISSIONS_FILENAME,
            "voice": VOICE_FILENAME,
            "memory": MEMORY_FILENAME,
            "plugins": PLUGINS_FILENAME,
            "filesystem": FILESYSTEM_FILENAME,
            "cowork": COWORK_FILENAME,
            "vault": VAULT_FILENAME,
            "execution": EXECUTION_FILENAME,
            "planning": PLANNING_FILENAME,
            "security": SECURITY_FILENAME,
            "workflow": WORKFLOW_FILENAME,
        }

    def _load_all(self) -> LoadedConfig:
        errors: list[str] = []
        values: dict[str, Any] = {}

        def _load(key: str, model: type, filename: str, *, overrides: dict | None = None) -> None:
            try:
                values[key] = load_typed_config(
                    model, self._config_dir / filename, overrides=overrides
                )
            except ConfigurationError as exc:
                errors.append(str(exc))

        _load("settings", Settings, SETTINGS_FILENAME, overrides=env_overrides())
        _load("permissions", PermissionsConfig, PERMISSIONS_FILENAME)
        _load("voice", VoiceConfig, VOICE_FILENAME)
        _load("memory", MemoryConfig, MEMORY_FILENAME)
        _load("plugins", PluginsConfig, PLUGINS_FILENAME)
        _load("filesystem", FilesystemConfig, FILESYSTEM_FILENAME)
        _load("cowork", CoworkConfig, COWORK_FILENAME)
        _load("vault", VaultConfig, VAULT_FILENAME)
        _load("execution", ExecutionConfig, EXECUTION_FILENAME)
        _load("planning", PlanningConfig, PLANNING_FILENAME)
        _load("security", SecurityConfig, SECURITY_FILENAME)
        _load("workflow", WorkflowConfig, WORKFLOW_FILENAME)

        if errors:
            raise ConfigurationError(
                f"Failed to load configuration from {self._config_dir}:\n\n" + "\n\n".join(errors)
            )

        return LoadedConfig(**values)

    def _publish(self, name: str, payload: dict[str, Any]) -> None:
        if self._events is not None:
            self._events.publish(name, payload, source="config_manager")
