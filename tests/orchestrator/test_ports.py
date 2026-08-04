from __future__ import annotations

from datetime import UTC, datetime

from jarvis.orchestrator.models import Turn
from jarvis.orchestrator.ports import (
    AutomationAction,
    AutomationPort,
    MemoryPort,
    NullAutomationPort,
    NullMemoryPort,
)


def test_null_memory_port_satisfies_protocol() -> None:
    assert isinstance(NullMemoryPort(), MemoryPort)


def test_null_automation_port_satisfies_protocol() -> None:
    assert isinstance(NullAutomationPort(), AutomationPort)


def test_null_memory_recall_returns_empty_list() -> None:
    assert NullMemoryPort().recall("s1", "anything") == []


def test_null_memory_remember_does_not_raise() -> None:
    turn = Turn(
        request_text="hi", response_text="hello", intent_name="greet", timestamp=datetime.now(UTC)
    )
    NullMemoryPort().remember("s1", turn)  # must not raise


def test_null_automation_execute_reports_failure() -> None:
    result = NullAutomationPort().execute(AutomationAction(name="click"))
    assert result.success is False
    assert result.error is not None
