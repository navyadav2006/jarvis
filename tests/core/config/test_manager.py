from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from jarvis.core.config.manager import ConfigManager
from jarvis.core.events import Event, EventBus
from jarvis.core.exceptions import ConfigurationError

from .conftest import write_yaml


def test_loads_defaults_when_no_files_exist(config_dir: Path) -> None:
    manager = ConfigManager(config_dir=config_dir)
    assert manager.settings.app.name == "Jarvis"
    assert manager.permissions.default_policy == "deny"
    assert manager.voice.enabled is False
    assert manager.memory.long_term.enabled is False
    assert manager.plugins.autoload is True
    assert manager.filesystem.require_confirmation == ["delete", "move", "rename"]


def test_loads_values_from_yaml_files(config_dir: Path) -> None:
    write_yaml(config_dir / "settings.yaml", {"app": {"name": "Custom"}})
    write_yaml(config_dir / "permissions.yaml", {"default_policy": "allow"})

    manager = ConfigManager(config_dir=config_dir)

    assert manager.settings.app.name == "Custom"
    assert manager.permissions.default_policy == "allow"


def test_invalid_yaml_at_startup_raises(config_dir: Path) -> None:
    (config_dir / "settings.yaml").write_text("app: [unclosed", encoding="utf-8")
    with pytest.raises(ConfigurationError):
        ConfigManager(config_dir=config_dir)


def test_startup_aggregates_errors_across_multiple_files(config_dir: Path) -> None:
    (config_dir / "settings.yaml").write_text("app: [unclosed", encoding="utf-8")
    write_yaml(config_dir / "voice.yaml", {"wake_word": {"threshold": 5.0}})

    with pytest.raises(ConfigurationError) as excinfo:
        ConfigManager(config_dir=config_dir)

    message = str(excinfo.value)
    assert "settings.yaml" in message
    assert "voice.yaml" in message


def test_snapshot_returns_all_nine_domains(config_dir: Path) -> None:
    manager = ConfigManager(config_dir=config_dir)
    snapshot = manager.snapshot()
    assert snapshot.settings is not None
    assert snapshot.permissions is not None
    assert snapshot.voice is not None
    assert snapshot.memory is not None
    assert snapshot.plugins is not None
    assert snapshot.filesystem is not None
    assert snapshot.cowork is not None
    assert snapshot.vault is not None
    assert snapshot.execution is not None
    assert snapshot.planning is not None
    assert snapshot.security is not None
    assert snapshot.workflow is not None


def test_reload_picks_up_changed_value(config_dir: Path) -> None:
    write_yaml(config_dir / "settings.yaml", {"app": {"name": "Before"}})
    manager = ConfigManager(config_dir=config_dir)

    write_yaml(config_dir / "settings.yaml", {"app": {"name": "After"}})
    changed = manager.reload()

    assert changed is True
    assert manager.settings.app.name == "After"


def test_reload_with_no_changes_returns_false(config_dir: Path) -> None:
    manager = ConfigManager(config_dir=config_dir)
    assert manager.reload() is False


def test_reload_publishes_config_reloaded_event(config_dir: Path) -> None:
    write_yaml(config_dir / "settings.yaml", {"app": {"name": "Before"}})
    events = EventBus()
    manager = ConfigManager(config_dir=config_dir, events=events)

    received: list[Event] = []
    events.subscribe("config.reloaded", received.append)

    write_yaml(config_dir / "settings.yaml", {"app": {"name": "After"}})
    manager.reload()

    assert len(received) == 1


def test_failed_reload_keeps_previous_config(config_dir: Path) -> None:
    write_yaml(config_dir / "settings.yaml", {"app": {"name": "Good"}})
    manager = ConfigManager(config_dir=config_dir)

    (config_dir / "settings.yaml").write_text("app: [unclosed", encoding="utf-8")
    changed = manager.reload()

    assert changed is False
    assert manager.settings.app.name == "Good"


def test_failed_reload_publishes_config_reload_failed_event(config_dir: Path) -> None:
    events = EventBus()
    manager = ConfigManager(config_dir=config_dir, events=events)

    received: list[Event] = []
    events.subscribe("config.reload_failed", received.append)

    (config_dir / "settings.yaml").write_text("app: [unclosed", encoding="utf-8")
    manager.reload()

    assert len(received) == 1
    assert "settings.yaml" in received[0].payload["error"]


def test_attach_events_wires_in_bus_after_construction(config_dir: Path) -> None:
    manager = ConfigManager(config_dir=config_dir)
    events = EventBus()
    manager.attach_events(events)

    received: list[Event] = []
    events.subscribe("config.reloaded", received.append)

    write_yaml(config_dir / "settings.yaml", {"app": {"name": "Changed"}})
    manager.reload()

    assert len(received) == 1


def test_watcher_detects_file_change_and_reloads(config_dir: Path) -> None:
    write_yaml(config_dir / "settings.yaml", {"app": {"name": "Before"}})
    manager = ConfigManager(config_dir=config_dir)

    try:
        manager.start_watching(poll_interval_seconds=0.02)
        settings_path = config_dir / "settings.yaml"
        write_yaml(settings_path, {"app": {"name": "After"}})
        # Force the mtime forward in case the filesystem's clock resolution
        # is coarser than the time between the two writes in this test.
        future = time.time() + 5
        os.utime(settings_path, (future, future))

        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and manager.settings.app.name != "After":
            time.sleep(0.02)

        assert manager.settings.app.name == "After"
    finally:
        manager.stop_watching()


def test_start_watching_is_idempotent(config_dir: Path) -> None:
    manager = ConfigManager(config_dir=config_dir)
    manager.start_watching(poll_interval_seconds=0.5)
    first_thread = manager._watch_thread
    manager.start_watching(poll_interval_seconds=0.5)
    assert manager._watch_thread is first_thread
    manager.stop_watching()


def test_stop_watching_without_start_is_a_noop(config_dir: Path) -> None:
    manager = ConfigManager(config_dir=config_dir)
    manager.stop_watching()  # must not raise
