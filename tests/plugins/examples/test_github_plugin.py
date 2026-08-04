from __future__ import annotations

import sys

import pytest

from jarvis.core.exceptions import ExecutionBackendUnavailableError
from jarvis.orchestrator.capability_registry import CapabilityRegistry
from jarvis.plugins.examples.github_plugin import GitHubPlugin

from .conftest import make_container_and_events, make_context


def test_on_load_registers_capability() -> None:
    container, events = make_container_and_events()
    registry = CapabilityRegistry()
    container.register_instance(CapabilityRegistry, registry)

    GitHubPlugin().on_load(container, events)

    assert registry.get("github_list_issues") is not None


def test_list_issues_without_configuration_reports_clearly() -> None:
    plugin = GitHubPlugin()
    plugin.configure({})

    result = plugin._list_issues(make_context())

    assert "not configured" in result.text


def test_missing_httpx_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "httpx", None)
    plugin = GitHubPlugin()
    plugin.configure({"repo": "org/repo"})

    with pytest.raises(ExecutionBackendUnavailableError):
        plugin._list_issues(make_context())
