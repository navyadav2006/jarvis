from __future__ import annotations

import pytest

from jarvis.core.version_utils import parse_dependency, parse_version, satisfies


def test_parse_version_simple() -> None:
    assert parse_version("1.2.3") == (1, 2, 3)


def test_parse_version_missing_segments_default_to_zero_when_compared() -> None:
    assert satisfies("1.2", ">=", "1.2.0")


def test_parse_dependency_with_constraint() -> None:
    assert parse_dependency("docker>=1.0.0") == ("docker", ">=", "1.0.0")


def test_parse_dependency_without_constraint() -> None:
    assert parse_dependency("docker") == ("docker", None, None)


def test_parse_dependency_malformed_raises() -> None:
    with pytest.raises(ValueError):
        parse_dependency("!!!not a name!!!")


@pytest.mark.parametrize(
    ("actual", "op", "required", "expected"),
    [
        ("2.0.0", ">=", "1.0.0", True),
        ("1.0.0", ">=", "2.0.0", False),
        ("1.0.0", "==", "1.0.0", True),
        ("1.0.1", "==", "1.0.0", False),
        ("1.0.0", "<=", "1.0.0", True),
        ("2.0.0", "<", "1.0.0", False),
        ("0.5.0", "<", "1.0.0", True),
    ],
)
def test_satisfies_operators(actual: str, op: str, required: str, expected: bool) -> None:
    assert satisfies(actual, op, required) is expected


def test_satisfies_with_no_constraint_always_true() -> None:
    assert satisfies("1.0.0", None, None) is True
