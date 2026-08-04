"""Shared loading/validation machinery for every config domain.

Every domain config (Settings, PermissionsConfig, VoiceConfig,
MemoryConfig, PluginsConfig) is loaded the same way: read a YAML file
into a dict (a missing file becomes `{}`, so the typed model's own
defaults apply), optionally merge environment-variable overrides on
top, then validate the result against a pydantic model. Centralizing
that here means all five domains get identical error handling and
override semantics for free, and a sixth domain added later only
needs a model class, not new plumbing.

`pydantic-settings` was deliberately not used for this (see
docs/architecture.md's Phase 3 section): it has no supported way to
point an existing `BaseSettings` subclass at an arbitrary YAML path at
*instance* construction time, which `ConfigManager` needs (it loads
from a configurable `config_dir`, not always the same fixed path — for
tests, that's `tmp_path`). Since `.env` is loaded into the real process
environment by `python-dotenv` before this module ever runs (see
main.bootstrap()), reading `os.environ` here already reflects both
real environment variables and `.env`, with real env vars winning per
python-dotenv's default `override=False` — so this module only has to
implement one precedence layer (env-derived dict over YAML-derived
dict), not three.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, TypeVar

import yaml
from pydantic import BaseModel, ValidationError

from jarvis.core.exceptions import ConfigurationError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def read_yaml_mapping(path: Path) -> dict[str, Any]:
    """Read `path` as a YAML mapping. A missing file is not an error —
    it means "use defaults" — but a file that exists and is malformed,
    or whose top level isn't a mapping, is.
    """
    if not path.exists():
        logger.debug("Config file %s does not exist; using defaults", path)
        return {}

    try:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"{path}: invalid YAML — {exc}") from exc

    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigurationError(
            f"{path}: expected a YAML mapping at the top level, got {type(data).__name__}"
        )
    return data


def env_overrides(*, environ: dict[str, str] | None = None) -> dict[str, Any]:
    """Collect `FOO__BAR__BAZ=value` environment variables into a nested
    dict (`{"foo": {"bar": {"baz": "value"}}}`) suitable for merging over
    YAML-sourced config before validation.

    Only keys containing at least one `__` are considered, and at least
    two segments are required (a section and a field) — this is what
    keeps ordinary environment variables (`PATH`, `HOME`, ...) from ever
    being mistaken for config.
    """
    source = environ if environ is not None else os.environ
    nested: dict[str, Any] = {}
    for key, value in source.items():
        if "__" not in key:
            continue
        parts = [part.lower() for part in key.split("__") if part]
        if len(parts) < 2:
            continue
        cursor = nested
        for part in parts[:-1]:
            cursor = cursor.setdefault(part, {})
        cursor[parts[-1]] = value
    return nested


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge `override` onto `base`, without mutating either.
    A dict value merges into a dict value; anything else in `override`
    replaces the corresponding value in `base` outright.
    """
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_typed_config(model: type[T], path: Path, *, overrides: dict[str, Any] | None = None) -> T:
    """Load `path` as YAML, merge `overrides` on top if given, and validate
    against `model`. Raises ConfigurationError — never a raw pydantic
    ValidationError or yaml.YAMLError — so every caller has one
    exception type to handle regardless of what went wrong.
    """
    raw = read_yaml_mapping(path)
    merged = deep_merge(raw, overrides) if overrides else raw
    try:
        return model.model_validate(merged)
    except ValidationError as exc:
        raise ConfigurationError(_format_validation_error(path, exc)) from exc


def _format_validation_error(path: Path, exc: ValidationError) -> str:
    lines = [f"{path}: {exc.error_count()} validation error(s):"]
    for error in exc.errors():
        field = ".".join(str(part) for part in error["loc"]) or "<root>"
        lines.append(f"  - {field}: {error['msg']}")
    return "\n".join(lines)
