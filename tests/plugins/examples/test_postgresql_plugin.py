from __future__ import annotations

import subprocess

from jarvis.orchestrator.capability_registry import CapabilityRegistry
from jarvis.plugins.examples.postgresql_plugin import PostgresPlugin

from .conftest import make_container_and_events, make_context


def test_on_load_registers_capability() -> None:
    container, events = make_container_and_events()
    registry = CapabilityRegistry()
    container.register_instance(CapabilityRegistry, registry)

    PostgresPlugin().on_load(container, events)

    assert registry.get("postgresql_query") is not None


def test_query_without_configuration_reports_clearly() -> None:
    plugin = PostgresPlugin()
    plugin.configure({})

    result = plugin._run_query(make_context(metadata={"query": "SELECT 1"}))

    assert "not configured" in result.text


def test_query_without_query_text_reports_clearly() -> None:
    plugin = PostgresPlugin()
    plugin.configure({"connection_string": "postgresql://x"})

    result = plugin._run_query(make_context(metadata={}))

    assert "No SQL query" in result.text


def test_query_runs_psql_and_returns_output(monkeypatch) -> None:
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args, 0, stdout="1 row", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    plugin = PostgresPlugin()
    plugin.configure({"connection_string": "postgresql://x"})
    result = plugin._run_query(make_context(metadata={"query": "SELECT 1"}))

    assert result.text == "1 row"
