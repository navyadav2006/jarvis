"""Integration test for the full startup sequence, using the real
config/*.yaml files shipped in the repo (they're the actual defaults
new developers get, so this doubles as a check that they're valid).
"""

from __future__ import annotations

import inspect

import jarvis.main
from jarvis.core.config import ConfigManager, Settings
from jarvis.core.events import EventBus
from jarvis.core.logging_setup import reset_logging_state_for_tests
from jarvis.core.plugin_loader import PluginLoader
from jarvis.core.workflow import WorkflowEngine, WorkflowRunner, WorkflowScheduler
from jarvis.main import bootstrap
from jarvis.orchestrator.capability_registry import CapabilityRegistry
from jarvis.orchestrator.orchestrator import Orchestrator


def _shutdown(container) -> None:
    """bootstrap() always starts background threads (config watcher,
    WorkflowRunner's worker pool, WorkflowScheduler) that must be
    stopped explicitly, or every test calling bootstrap() leaks them
    for the rest of the test session.
    """
    container.resolve(ConfigManager).stop_watching()
    container.resolve(WorkflowScheduler).stop()
    container.resolve(WorkflowRunner).stop()


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
