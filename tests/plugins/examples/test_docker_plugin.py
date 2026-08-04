from __future__ import annotations

import subprocess

from jarvis.orchestrator.capability_registry import CapabilityRegistry
from jarvis.plugins.examples.docker_plugin import DockerPlugin

from .conftest import make_container_and_events, make_context


def test_on_load_registers_capability() -> None:
    container, events = make_container_and_events()
    registry = CapabilityRegistry()
    container.register_instance(CapabilityRegistry, registry)

    DockerPlugin().on_load(container, events)

    assert registry.get("docker_list_containers") is not None


def test_list_containers_reports_no_docker_cli(monkeypatch) -> None:
    def fake_run(*args, **kwargs):
        raise FileNotFoundError("docker not found")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = DockerPlugin()._list_containers(make_context())

    assert "Could not run docker" in result.text


def test_list_containers_reports_output(monkeypatch) -> None:
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args, 0, stdout="web\tUp 2 hours\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = DockerPlugin()._list_containers(make_context())

    assert "web" in result.text


def test_list_containers_reports_empty_when_none_running(monkeypatch) -> None:
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = DockerPlugin()._list_containers(make_context())

    assert result.text == "No containers are running."
