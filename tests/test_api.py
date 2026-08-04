from __future__ import annotations

import dataclasses
from pathlib import Path

from fastapi.testclient import TestClient

from jarvis.api.app import create_app
from jarvis.core.config import ConfigManager, Settings
from jarvis.core.config.filesystem_config import FilesystemConfig
from jarvis.core.config.manager import LoadedConfig
from jarvis.core.container import ServiceContainer
from jarvis.core.cowork.ports import NullCoworkClientPort
from jarvis.core.events import EventBus
from jarvis.core.filesystem import LocalFilesystemService
from jarvis.orchestrator.capability_registry import CapabilityRegistry
from jarvis.orchestrator.intent_recognizer import PatternIntentRecognizer
from jarvis.orchestrator.models import CapabilityContext, CapabilityResult
from jarvis.orchestrator.orchestrator import Orchestrator
from jarvis.orchestrator.ports import NullAutomationPort, NullMemoryPort
from jarvis.orchestrator.session_store import SessionStore


def _build_container_with_orchestrator() -> ServiceContainer:
    container = ServiceContainer()
    container.register_instance(Settings, Settings())

    events = EventBus()
    registry = CapabilityRegistry()
    orchestrator = Orchestrator(
        events=events,
        capability_registry=registry,
        intent_recognizer=PatternIntentRecognizer(registry),
        session_store=SessionStore(),
        memory=NullMemoryPort(),
        automation=NullAutomationPort(),
        # Empty allowlist: denies everything, a safe stand-in for tests
        # that don't exercise the filesystem module itself.
        filesystem=LocalFilesystemService(FilesystemConfig(allowed_dirs=[])),
        cowork=NullCoworkClientPort(),
    )
    container.register_instance(Orchestrator, orchestrator)
    container.register_instance(CapabilityRegistry, registry)
    return container


def test_health_endpoint_reports_status() -> None:
    container = _build_container_with_orchestrator()

    app = create_app(container)
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "Jarvis"
    assert body["plugins_loaded"] == []


def test_message_endpoint_returns_unhandled_for_unknown_text() -> None:
    container = _build_container_with_orchestrator()
    client = TestClient(create_app(container))

    response = client.post("/message", json={"text": "gibberish", "session_id": "s1"})

    assert response.status_code == 200
    body = response.json()
    assert body["handled"] is False
    assert body["intent"] == "unknown"


def test_message_endpoint_routes_to_registered_capability() -> None:
    container = _build_container_with_orchestrator()
    registry = container.resolve(CapabilityRegistry)

    def handler(context: CapabilityContext) -> CapabilityResult:
        return CapabilityResult(text="hi there")

    registry.register("greet", handler, patterns=[r"\bhello\b"], plugin="greeter")

    client = TestClient(create_app(container))
    response = client.post("/message", json={"text": "hello", "session_id": "s1"})

    assert response.status_code == 200
    body = response.json()
    assert body["handled"] is True
    assert body["text"] == "hi there"
    assert body["intent"] == "greet"


def test_config_endpoint_returns_empty_dict_without_config_manager() -> None:
    container = _build_container_with_orchestrator()
    client = TestClient(create_app(container))

    response = client.get("/config")

    assert response.status_code == 200
    assert response.json() == {}


def test_config_endpoint_returns_every_config_domain(tmp_path: Path) -> None:
    # Asserted against LoadedConfig's own fields, not a hand-written
    # set of names — this is the regression test for a real Phase 21
    # finding: the route drifted for 5 phases, silently returning only
    # its original 7 domains while ConfigManager grew to 12, and a
    # test asserting a fixed set of 7 keys was masking it.
    container = _build_container_with_orchestrator()
    container.register_instance(ConfigManager, ConfigManager(config_dir=tmp_path / "config"))
    client = TestClient(create_app(container))

    response = client.get("/config")

    assert response.status_code == 200
    body = response.json()
    expected_domains = {f.name for f in dataclasses.fields(LoadedConfig)}
    assert set(body.keys()) == expected_domains
    assert body["settings"]["app"]["name"] == "Jarvis"
    assert body["permissions"]["default_policy"] == "deny"
    assert body["workflow"]["max_concurrent_runs"] == 2
    assert body["security"]["session_history_limit"] == 200


def test_health_endpoint_reflects_live_reloaded_settings(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "settings.yaml").write_text("app:\n  name: Before\n", encoding="utf-8")

    container = _build_container_with_orchestrator()
    config_manager = ConfigManager(config_dir=config_dir)
    container.register_instance(ConfigManager, config_manager)
    client = TestClient(create_app(container))

    assert client.get("/health").json()["app"] == "Before"

    (config_dir / "settings.yaml").write_text("app:\n  name: After\n", encoding="utf-8")
    config_manager.reload()

    assert client.get("/health").json()["app"] == "After"
