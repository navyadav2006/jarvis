"""Minimal, dependency-free dotted-version comparison — "Versioning"
for the plugin framework (Phase 18). Not full PEP 440/semver (no
pre-release/build-metadata handling); good enough for comparing plain
"major.minor.patch"-style plugin versions, the same "real, useful
default without a new dependency" choice made throughout this project
(e.g. core/execution/'s stdlib-only terminal/application handlers).
"""

from __future__ import annotations

import re

_CONSTRAINT_RE = re.compile(r"^([a-zA-Z0-9_\-]+)\s*(>=|<=|==|>|<)?\s*([\w.\-]+)?$")


def parse_version(version: str) -> tuple[int, ...]:
    parts = []
    for segment in version.split("."):
        digits = "".join(ch for ch in segment if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def _compare(a: tuple[int, ...], b: tuple[int, ...]) -> int:
    length = max(len(a), len(b))
    a = a + (0,) * (length - len(a))
    b = b + (0,) * (length - len(b))
    return (a > b) - (a < b)


def parse_dependency(spec: str) -> tuple[str, str | None, str | None]:
    """"docker>=1.0.0" -> ("docker", ">=", "1.0.0"); "docker" -> ("docker", None, None)."""
    match = _CONSTRAINT_RE.match(spec.strip())
    if not match:
        raise ValueError(f"malformed dependency spec: {spec!r}")
    name, operator, version = match.groups()
    return name, operator, version


def satisfies(actual_version: str, operator: str | None, required_version: str | None) -> bool:
    if operator is None or required_version is None:
        return True
    comparison = _compare(parse_version(actual_version), parse_version(required_version))
    return {
        ">=": comparison >= 0,
        "<=": comparison <= 0,
        "==": comparison == 0,
        ">": comparison > 0,
        "<": comparison < 0,
    }[operator]
