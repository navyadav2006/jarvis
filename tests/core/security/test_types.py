from __future__ import annotations

from jarvis.core.security.types import PermissionLevel


def test_levels_are_ordered_by_risk() -> None:
    assert PermissionLevel.READ < PermissionLevel.WRITE < PermissionLevel.EXECUTE
    assert PermissionLevel.EXECUTE < PermissionLevel.ADMINISTRATOR < PermissionLevel.DANGEROUS
    assert PermissionLevel.DANGEROUS < PermissionLevel.BLOCKED


def test_label_is_lowercase_name() -> None:
    assert PermissionLevel.READ.label == "read"
    assert PermissionLevel.ADMINISTRATOR.label == "administrator"
    assert PermissionLevel.BLOCKED.label == "blocked"
