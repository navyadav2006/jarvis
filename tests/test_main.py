"""Integration test for the full startup sequence, using the real
config/*.yaml files shipped in the repo (they're the actual defaults
new developers get, so this doubles as a check that they're valid).
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

import jarvis.main
from jarvis.core.config import ConfigManager, Settings
from jarvis.core.events import EventBus
from jarvis.core.exceptions import SpeechBackendUnavailableError
from jarvis.core.logging_setup import reset_logging_state_for_tests
from jarvis.core.plugin_loader import PluginLoader
from jarvis.core.speech import JarvisVoicePipeline
from jarvis.core.workflow import WorkflowEngine, WorkflowRunner, WorkflowScheduler
from jarvis.main import bootstrap
from jarvis.orchestrator.capability_registry import CapabilityRegistry
from jarvis.orchestrator.orchestrator import Orchestrator


def _shutdown(container) -> None:
    """bootstrap() always starts background threads (config watcher,
    WorkflowRunner's worker pool, WorkflowScheduler, and — when
    voice.yaml's `enabled` is true, as it now is in this repo's
    checked-in config — JarvisVoicePipeline's mic-capture thread) that
    must be stopped explicitly, or every test calling bootstrap() leaks
    them for the rest of the test session.
    """
    container.resolve(ConfigManager).stop_watching()
    container.resolve(WorkflowScheduler).stop()
    container.resolve(WorkflowRunner).stop()
    if container.has(JarvisVoicePipeline):
        container.resolve(JarvisVoicePipeline).stop()


def test_bootstrap_wires_every_core_service() -> None:
    reset_logging_state_for_tests()
    container = bootstrap()
    try:
        assert container.has(ConfigManager)
        assert container.has(Settings)
        assert container.has(EventBus)
        assert container.has(CapabilityRegistry)
        assert container.has(Orchestrator)
        assert container.has(PluginLoader)
        assert container.has(WorkflowEngine)
    finally:
        _shutdown(container)
        reset_logging_state_for_tests()


def test_bootstrap_starts_config_watcher_when_live_reload_enabled() -> None:
    reset_logging_state_for_tests()
    container = bootstrap()
    try:
        config_manager = container.resolve(ConfigManager)
        if config_manager.settings.config.live_reload:
            assert config_manager._watch_thread is not None
            assert config_manager._watch_thread.is_alive()
    finally:
        _shutdown(container)
        reset_logging_state_for_tests()


def test_bootstrap_starts_workflow_runner_and_scheduler() -> None:
    reset_logging_state_for_tests()
    container = bootstrap()
    try:
        runner = container.resolve(WorkflowRunner)
        scheduler = container.resolve(WorkflowScheduler)
        assert runner._workers
        assert all(w.is_alive() for w in runner._workers)
        assert scheduler._thread is not None
        assert scheduler._thread.is_alive()
    finally:
        _shutdown(container)
        reset_logging_state_for_tests()


def test_bootstrap_starts_no_voice_pipeline_when_voice_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A temp config dir, not the repo's checked-in config/voice.yaml —
    # this deployment's voice.yaml is intentionally enabled: true (a
    # real mic/speaker + downloaded models are present on this
    # machine), so this test asserts the disabled *mechanism* still
    # works, independent of whatever the shipped default currently is.
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "voice.yaml").write_text("enabled: false\n", encoding="utf-8")
    monkeypatch.setattr(jarvis.main, "DEFAULT_CONFIG_DIR", config_dir)

    reset_logging_state_for_tests()
    container = bootstrap()
    try:
        assert not container.has(JarvisVoicePipeline)
    finally:
        _shutdown(container)
        reset_logging_state_for_tests()


def test_bootstrap_raises_clear_error_when_voice_enabled_without_extra_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # voice.yaml's `enabled: true` is an explicit request for a real
    # backend — bootstrap() must fail fast and clearly (not silently
    # fall back, not raise a bare ImportError) when the 'voice' extra
    # isn't installed, the same "config validation failure is fatal"
    # posture the rest of bootstrap() already has. sounddevice IS
    # installed in this environment (voice is genuinely enabled here),
    # so the missing-backend path is simulated via sys.modules rather
    # than relying on the extra actually being absent.
    monkeypatch.setitem(sys.modules, "sounddevice", None)
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "voice.yaml").write_text("enabled: true\n", encoding="utf-8")
    monkeypatch.setattr(jarvis.main, "DEFAULT_CONFIG_DIR", config_dir)

    reset_logging_state_for_tests()
    try:
        with pytest.raises(SpeechBackendUnavailableError):
            bootstrap()
    finally:
        reset_logging_state_for_tests()


def test_uvicorn_is_not_imported_at_module_level() -> None:
    """Startup-latency regression test (Phase 21): uvicorn (and the
    watchfiles/click/anyio it pulls in, ~0.4s) must stay a lazy,
    function-local import inside main() so bootstrap()-only callers —
    every test in this suite, scripts, create_app() itself — don't pay
    for it.
    """
    source = inspect.getsource(jarvis.main)
    module_level_source = source.split("\ndef main() -> None:")[0]
    assert "import uvicorn" not in module_level_source
    assert "import uvicorn" in inspect.getsource(jarvis.main.main)
