from __future__ import annotations

from pathlib import Path

from jarvis.core.config.filesystem_config import FilesystemConfig
from jarvis.core.config.permissions_config import PermissionRule, PermissionsConfig
from jarvis.core.config.security_config import RateLimitConfig, SecurityConfig
from jarvis.core.events import EventBus
from jarvis.core.security.confirmation import AutoDenyConfirmation, CallbackConfirmation
from jarvis.core.security.manager import SecurityManager
from jarvis.core.security.types import PermissionLevel, SecurityRequest


def _manager(
    tmp_path: Path,
    *,
    rules: list[PermissionRule] | None = None,
    default_policy: str = "deny",
    rate_limits: RateLimitConfig | None = None,
    confirmation=None,
    events: EventBus | None = None,
    confirmation_required_levels: list[str] | None = None,
) -> SecurityManager:
    permissions = PermissionsConfig(default_policy=default_policy, rules=rules or [])
    security_config = SecurityConfig(
        audit_log_path=tmp_path / "audit.jsonl",
        rate_limits=rate_limits or RateLimitConfig(),
        confirmation_required_levels=confirmation_required_levels
        or ["dangerous", "administrator"],
    )
    return SecurityManager(
        security_config,
        filesystem_config=FilesystemConfig(allowed_dirs=[tmp_path]),
        permissions=permissions,
        confirmation=confirmation or AutoDenyConfirmation(),
        events=events,
        root=tmp_path,
    )


def _allowed_request(**overrides) -> SecurityRequest:
    defaults = dict(category="clipboard", action="get", requested_by="cowork")
    defaults.update(overrides)
    return SecurityRequest(**defaults)


# -- basic allow/deny -------------------------------------------------------


def test_allows_when_permitted(tmp_path: Path) -> None:
    mgr = _manager(
        tmp_path, rules=[PermissionRule(plugin="cowork", allow=["clipboard.read"])]
    )
    decision = mgr.authorize(_allowed_request())
    assert decision.allowed is True
    assert decision.level == PermissionLevel.READ


def test_denies_when_permissions_yaml_denies(tmp_path: Path) -> None:
    mgr = _manager(tmp_path, rules=[])
    decision = mgr.authorize(_allowed_request())
    assert decision.allowed is False
    assert "clipboard.read" in decision.reason


def test_unrecognized_action_is_blocked_before_permissions_are_even_checked(
    tmp_path: Path,
) -> None:
    mgr = _manager(tmp_path, default_policy="allow")
    decision = mgr.authorize(_allowed_request(category="nope", action="nope"))
    assert decision.allowed is False
    assert decision.level == PermissionLevel.BLOCKED


# -- rate limiting ------------------------------------------------------


def test_rate_limit_denies_after_the_configured_count(tmp_path: Path) -> None:
    mgr = _manager(
        tmp_path,
        rules=[PermissionRule(plugin="cowork", allow=["clipboard.read"])],
        rate_limits=RateLimitConfig(read_per_minute=2),
    )
    assert mgr.authorize(_allowed_request()).allowed is True
    assert mgr.authorize(_allowed_request()).allowed is True
    third = mgr.authorize(_allowed_request())
    assert third.allowed is False
    assert "rate limit" in third.reason


def test_rate_limit_check_runs_before_permission_scope_check(tmp_path: Path) -> None:
    # No permission grant at all -- if rate limiting ran after the
    # permission check we'd never see the rate-limit reason, since the
    # request would already be denied for a different cause. Confirm
    # the denial is scope-related (permission), not rate-limit, proving
    # order: BLOCKED check < rate limit < scope check, i.e. an allowed
    # scope run past its limit is denied for the *rate* reason.
    mgr = _manager(
        tmp_path,
        rules=[PermissionRule(plugin="cowork", allow=["clipboard.read"])],
        rate_limits=RateLimitConfig(read_per_minute=1),
    )
    mgr.authorize(_allowed_request())
    second = mgr.authorize(_allowed_request())
    assert second.allowed is False
    assert "rate limit" in second.reason


# -- filesystem allow/deny -------------------------------------------------


def test_denies_path_outside_allowed_dirs(tmp_path: Path) -> None:
    mgr = _manager(
        tmp_path, rules=[PermissionRule(plugin="cowork", allow=["filesystem.read"])]
    )
    outside = tmp_path.parent / "elsewhere.txt"
    decision = mgr.authorize(
        SecurityRequest(
            category="filesystem", action="read", requested_by="cowork", path=str(outside)
        )
    )
    assert decision.allowed is False


def test_allows_path_inside_allowed_dirs(tmp_path: Path) -> None:
    mgr = _manager(
        tmp_path, rules=[PermissionRule(plugin="cowork", allow=["filesystem.read"])]
    )
    inside = tmp_path / "ok.txt"
    decision = mgr.authorize(
        SecurityRequest(
            category="filesystem", action="read", requested_by="cowork", path=str(inside)
        )
    )
    assert decision.allowed is True


# -- confirmation ------------------------------------------------------


def test_dangerous_action_denied_when_confirmation_declines(tmp_path: Path) -> None:
    mgr = _manager(
        tmp_path,
        rules=[PermissionRule(plugin="cowork", allow=["filesystem.write"])],
        confirmation=AutoDenyConfirmation(),
    )
    decision = mgr.authorize(
        SecurityRequest(category="filesystem", action="delete", requested_by="cowork")
    )
    assert decision.allowed is False
    assert decision.required_confirmation is True


def test_dangerous_action_allowed_when_confirmation_accepts(tmp_path: Path) -> None:
    mgr = _manager(
        tmp_path,
        rules=[PermissionRule(plugin="cowork", allow=["filesystem.write"])],
        confirmation=CallbackConfirmation(lambda prompt: True),
    )
    decision = mgr.authorize(
        SecurityRequest(category="filesystem", action="delete", requested_by="cowork")
    )
    assert decision.allowed is True
    assert decision.required_confirmation is True


def test_read_level_never_asks_for_confirmation(tmp_path: Path) -> None:
    calls: list[str] = []
    mgr = _manager(
        tmp_path,
        rules=[PermissionRule(plugin="cowork", allow=["clipboard.read"])],
        confirmation=CallbackConfirmation(lambda prompt: calls.append(prompt) or True),
    )
    decision = mgr.authorize(_allowed_request())
    assert decision.allowed is True
    assert decision.required_confirmation is False
    assert calls == []


# -- emergency shutdown --------------------------------------------------


def test_emergency_shutdown_denies_everything_immediately(tmp_path: Path) -> None:
    mgr = _manager(tmp_path, rules=[PermissionRule(plugin="cowork", allow=["clipboard.read"])])
    mgr.trigger_emergency_shutdown("suspicious activity")
    decision = mgr.authorize(_allowed_request())
    assert decision.allowed is False
    assert "shutdown" in decision.reason
    assert mgr.is_shutdown is True


def test_resume_lifts_the_shutdown(tmp_path: Path) -> None:
    mgr = _manager(tmp_path, rules=[PermissionRule(plugin="cowork", allow=["clipboard.read"])])
    mgr.trigger_emergency_shutdown("test")
    mgr.resume("resolved")
    assert mgr.is_shutdown is False
    decision = mgr.authorize(_allowed_request())
    assert decision.allowed is True


def test_shutdown_publishes_event(tmp_path: Path) -> None:
    events = EventBus()
    received = []
    events.subscribe("security.emergency_shutdown", lambda e: received.append(e))
    mgr = _manager(tmp_path, events=events)
    mgr.trigger_emergency_shutdown("test reason")
    assert len(received) == 1


# -- session history + audit log recording -------------------------------


def test_every_decision_is_recorded_to_session_history(tmp_path: Path) -> None:
    mgr = _manager(tmp_path, rules=[PermissionRule(plugin="cowork", allow=["clipboard.read"])])
    mgr.authorize(_allowed_request())
    mgr.authorize(_allowed_request(action="set"))  # denied, no grant for clipboard.write

    history = mgr.session_history_for("cowork")
    assert len(history) == 2
    assert history[0].allowed is True
    assert history[1].allowed is False


def test_every_decision_is_recorded_to_audit_log(tmp_path: Path) -> None:
    mgr = _manager(tmp_path, rules=[PermissionRule(plugin="cowork", allow=["clipboard.read"])])
    mgr.authorize(_allowed_request())

    log = mgr.audit_log()
    assert len(log) == 1
    assert log[0]["category"] == "clipboard"
    assert log[0]["allowed"] is True


def test_denied_requests_are_also_audited(tmp_path: Path) -> None:
    mgr = _manager(tmp_path, rules=[])
    mgr.authorize(_allowed_request())
    log = mgr.audit_log()
    assert len(log) == 1
    assert log[0]["allowed"] is False
