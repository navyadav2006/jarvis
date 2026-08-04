from __future__ import annotations

import pytest
from pydantic import ValidationError

from jarvis.core.config.permissions_config import PermissionRule, PermissionsConfig


def test_default_policy_deny_with_no_rules_denies_everything() -> None:
    config = PermissionsConfig()
    assert config.is_allowed("any_plugin", "filesystem.read") is False


def test_default_policy_allow_with_no_rules_allows_everything() -> None:
    config = PermissionsConfig(default_policy="allow")
    assert config.is_allowed("any_plugin", "filesystem.read") is True


def test_exact_rule_allow_grants_scope() -> None:
    config = PermissionsConfig(
        rules=[PermissionRule(plugin="notes", allow=["filesystem.read"])]
    )
    assert config.is_allowed("notes", "filesystem.read") is True


def test_exact_rule_does_not_grant_unlisted_scope() -> None:
    config = PermissionsConfig(
        rules=[PermissionRule(plugin="notes", allow=["filesystem.read"])]
    )
    assert config.is_allowed("notes", "automation.mouse") is False


def test_deny_beats_allow_within_same_rule() -> None:
    config = PermissionsConfig(
        rules=[
            PermissionRule(
                plugin="notes", allow=["filesystem.read"], deny=["filesystem.read"]
            )
        ]
    )
    assert config.is_allowed("notes", "filesystem.read") is False


def test_exact_rule_takes_precedence_over_wildcard() -> None:
    config = PermissionsConfig(
        rules=[
            PermissionRule(plugin="*", allow=["filesystem.read"]),
            PermissionRule(plugin="notes", deny=["filesystem.read"]),
        ]
    )
    assert config.is_allowed("notes", "filesystem.read") is False


def test_wildcard_rule_applies_to_plugins_without_exact_rule() -> None:
    config = PermissionsConfig(rules=[PermissionRule(plugin="*", allow=["filesystem.read"])])
    assert config.is_allowed("anything", "filesystem.read") is True


def test_blank_plugin_name_is_rejected() -> None:
    with pytest.raises(ValidationError):
        PermissionRule(plugin="   ")


def test_invalid_default_policy_is_rejected() -> None:
    with pytest.raises(ValidationError):
        PermissionsConfig(default_policy="maybe")
