from __future__ import annotations

from jarvis.core.security.levels import LEVELS, PERMISSION_SCOPES, level_for, scope_for
from jarvis.core.security.types import PermissionLevel


def test_unmapped_action_defaults_to_blocked() -> None:
    assert level_for("not_a_category", "not_an_action") == PermissionLevel.BLOCKED


def test_known_actions_map_to_expected_levels() -> None:
    assert level_for("filesystem", "read") == PermissionLevel.READ
    assert level_for("filesystem", "delete") == PermissionLevel.DANGEROUS
    assert level_for("terminal", "run") == PermissionLevel.EXECUTE
    assert level_for("plugin", "install") == PermissionLevel.ADMINISTRATOR


def test_scope_for_unmapped_action_returns_none() -> None:
    assert scope_for("plugin", "install") is None
    assert scope_for("nope", "nope") is None


def test_every_level_entry_that_execution_engine_dispatches_has_a_scope() -> None:
    # ExecutionEngine dispatches everything except the plugin/security
    # actions Phase 18/19 added for classification only -- those two
    # are the only LEVELS entries allowed to have no PERMISSION_SCOPES
    # counterpart.
    dispatchable = {
        key: level
        for key, level in LEVELS.items()
        if key[0] not in {"plugin", "security"}
    }
    for key in dispatchable:
        assert key in PERMISSION_SCOPES, f"{key} has a level but no permission scope"


def test_permission_scopes_match_execution_engine_expectations() -> None:
    # Regression test for the Phase 19 bug: SecurityManager and
    # ExecutionEngine must agree on the scope string for the same
    # action, or a permissions.yaml rule written for one silently
    # doesn't unlock the other.
    assert scope_for("clipboard", "get") == "clipboard.read"
    assert scope_for("clipboard", "set") == "clipboard.write"
    assert scope_for("filesystem", "read") == "filesystem.read"
    assert scope_for("filesystem", "delete") == "filesystem.write"
    assert scope_for("desktop", "click") == "automation.mouse"
    assert scope_for("desktop", "type_text") == "automation.keyboard"
    assert scope_for("browser", "navigate") == "browser.control"


def test_execution_engine_imports_the_same_scope_table() -> None:
    from jarvis.core.execution.engine import PERMISSION_SCOPES as engine_scopes

    assert engine_scopes is PERMISSION_SCOPES
