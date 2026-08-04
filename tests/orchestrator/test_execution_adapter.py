from __future__ import annotations

from pathlib import Path

from jarvis.core.config.filesystem_config import FilesystemConfig
from jarvis.core.config.permissions_config import PermissionRule, PermissionsConfig
from jarvis.core.config.security_config import SecurityConfig
from jarvis.core.execution.types import ActionCategory, ExecutionRequest, ExecutionResult
from jarvis.core.security.confirmation import AutoDenyConfirmation
from jarvis.core.security.manager import SecurityManager
from jarvis.orchestrator.execution_adapter import ExecutionEngineAdapter
from jarvis.orchestrator.ports import AutomationAction, AutomationPort


class FakeEngine:
    def __init__(self, result: ExecutionResult | None = None) -> None:
        self.received: list[ExecutionRequest] = []
        self.result = result or ExecutionResult(success=True, output="ok")

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        self.received.append(request)
        return self.result


def test_adapter_satisfies_automation_port() -> None:
    assert isinstance(ExecutionEngineAdapter(FakeEngine()), AutomationPort)


def test_execute_splits_dotted_action_name_into_category_and_action() -> None:
    engine = FakeEngine()
    adapter = ExecutionEngineAdapter(engine, requested_by="cowork")

    adapter.execute(AutomationAction(name="filesystem.write", parameters={"path": "a"}))

    request = engine.received[0]
    assert request.category == ActionCategory.FILESYSTEM
    assert request.action == "write"
    assert request.parameters == {"path": "a"}
    assert request.requested_by == "cowork"


def test_execute_returns_automation_result_matching_engine_output() -> None:
    engine = FakeEngine(ExecutionResult(success=True, output={"exit_code": 0}))
    adapter = ExecutionEngineAdapter(engine)

    result = adapter.execute(AutomationAction(name="terminal.run", parameters={}))

    assert result.success is True
    assert result.output == {"exit_code": 0}


def test_execute_reports_failure_from_engine() -> None:
    engine = FakeEngine(ExecutionResult(success=False, error="denied"))
    adapter = ExecutionEngineAdapter(engine)

    result = adapter.execute(AutomationAction(name="desktop.click", parameters={}))

    assert result.success is False
    assert result.error == "denied"


def test_unknown_category_fails_gracefully_without_calling_engine() -> None:
    engine = FakeEngine()
    adapter = ExecutionEngineAdapter(engine)

    result = adapter.execute(AutomationAction(name="not_a_category.action", parameters={}))

    assert result.success is False
    assert engine.received == []


def test_action_name_without_a_dot_fails_gracefully() -> None:
    engine = FakeEngine()
    adapter = ExecutionEngineAdapter(engine)

    result = adapter.execute(AutomationAction(name="justonename", parameters={}))

    assert result.success is False


def _security_manager(
    tmp_path: Path, *, rules: list[PermissionRule] | None = None
) -> SecurityManager:
    permissions = PermissionsConfig(default_policy="deny", rules=rules or [])
    security_config = SecurityConfig(audit_log_path=tmp_path / "audit.jsonl")
    return SecurityManager(
        security_config,
        filesystem_config=FilesystemConfig(allowed_dirs=[tmp_path]),
        permissions=permissions,
        confirmation=AutoDenyConfirmation(),
        root=tmp_path,
    )


def test_security_denial_prevents_the_engine_from_ever_being_called(tmp_path: Path) -> None:
    engine = FakeEngine()
    security = _security_manager(tmp_path, rules=[])  # no grants -- everything denied
    adapter = ExecutionEngineAdapter(engine, requested_by="cowork", security=security)

    result = adapter.execute(AutomationAction(name="filesystem.delete", parameters={}))

    assert result.success is False
    assert engine.received == []


def test_security_allows_when_permitted_and_the_engine_still_runs(tmp_path: Path) -> None:
    engine = FakeEngine()
    security = _security_manager(
        tmp_path, rules=[PermissionRule(plugin="cowork", allow=["clipboard.read"])]
    )
    adapter = ExecutionEngineAdapter(engine, requested_by="cowork", security=security)

    result = adapter.execute(AutomationAction(name="clipboard.get", parameters={}))

    assert result.success is True
    assert len(engine.received) == 1


def test_no_security_manager_means_no_gate_at_all() -> None:
    # Default behaviour (security=None) is unchanged from pre-Phase-19:
    # every request reaches the engine directly.
    engine = FakeEngine()
    adapter = ExecutionEngineAdapter(engine, requested_by="cowork")

    result = adapter.execute(AutomationAction(name="filesystem.delete", parameters={}))

    assert result.success is True
    assert len(engine.received) == 1
