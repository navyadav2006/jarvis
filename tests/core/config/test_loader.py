from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel

from jarvis.core.config.loader import (
    deep_merge,
    env_overrides,
    load_typed_config,
    read_yaml_mapping,
)
from jarvis.core.exceptions import ConfigurationError

from .conftest import write_yaml


class _Nested(BaseModel):
    value: str = "default"


class _Model(BaseModel):
    name: str = "default-name"
    count: int = 0
    nested: _Nested = _Nested()


def test_read_yaml_mapping_missing_file_returns_empty_dict(tmp_path: Path) -> None:
    assert read_yaml_mapping(tmp_path / "nope.yaml") == {}


def test_read_yaml_mapping_reads_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "x.yaml"
    write_yaml(path, {"a": 1})
    assert read_yaml_mapping(path) == {"a": 1}


def test_read_yaml_mapping_empty_file_returns_empty_dict(tmp_path: Path) -> None:
    path = tmp_path / "x.yaml"
    path.write_text("", encoding="utf-8")
    assert read_yaml_mapping(path) == {}


def test_read_yaml_mapping_malformed_yaml_raises_configuration_error(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("key: [unclosed", encoding="utf-8")
    with pytest.raises(ConfigurationError):
        read_yaml_mapping(path)


def test_read_yaml_mapping_non_mapping_top_level_raises(tmp_path: Path) -> None:
    path = tmp_path / "list.yaml"
    path.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(ConfigurationError):
        read_yaml_mapping(path)


def test_env_overrides_ignores_unrelated_vars() -> None:
    assert env_overrides(environ={"PATH": "/usr/bin", "HOME": "/home/x"}) == {}


def test_env_overrides_requires_at_least_two_segments() -> None:
    assert env_overrides(environ={"SOLO": "x"}) == {}


def test_env_overrides_with_double_underscore_but_still_one_segment() -> None:
    # "__SOLO" contains "__" (so it isn't filtered by the unrelated-var
    # check) but splits+filters down to a single non-empty segment,
    # which still isn't enough to form a section.field pair.
    assert env_overrides(environ={"__SOLO": "x"}) == {}


def test_env_overrides_builds_nested_dict() -> None:
    result = env_overrides(environ={"APP__NAME": "Foo", "APP__DEBUG": "true"})
    assert result == {"app": {"name": "Foo", "debug": "true"}}


def test_env_overrides_supports_deep_nesting() -> None:
    result = env_overrides(environ={"A__B__C": "1"})
    assert result == {"a": {"b": {"c": "1"}}}


def test_deep_merge_overrides_scalar() -> None:
    assert deep_merge({"a": 1}, {"a": 2}) == {"a": 2}


def test_deep_merge_merges_nested_dicts() -> None:
    base = {"a": {"x": 1, "y": 2}}
    override = {"a": {"y": 3}}
    assert deep_merge(base, override) == {"a": {"x": 1, "y": 3}}


def test_deep_merge_does_not_mutate_inputs() -> None:
    base = {"a": {"x": 1}}
    override = {"a": {"y": 2}}
    deep_merge(base, override)
    assert base == {"a": {"x": 1}}
    assert override == {"a": {"y": 2}}


def test_load_typed_config_applies_defaults_for_missing_file(tmp_path: Path) -> None:
    model = load_typed_config(_Model, tmp_path / "missing.yaml")
    assert model.name == "default-name"
    assert model.nested.value == "default"


def test_load_typed_config_reads_yaml_values(tmp_path: Path) -> None:
    path = tmp_path / "x.yaml"
    write_yaml(path, {"name": "custom", "count": 5})
    model = load_typed_config(_Model, path)
    assert model.name == "custom"
    assert model.count == 5


def test_load_typed_config_applies_overrides_over_yaml(tmp_path: Path) -> None:
    path = tmp_path / "x.yaml"
    write_yaml(path, {"name": "from-yaml"})
    model = load_typed_config(_Model, path, overrides={"name": "from-env"})
    assert model.name == "from-env"


def test_load_typed_config_invalid_value_raises_configuration_error(tmp_path: Path) -> None:
    path = tmp_path / "x.yaml"
    write_yaml(path, {"count": "not-a-number"})
    with pytest.raises(ConfigurationError) as excinfo:
        load_typed_config(_Model, path)
    assert "count" in str(excinfo.value)


def test_load_typed_config_error_message_includes_path(tmp_path: Path) -> None:
    path = tmp_path / "broken.yaml"
    write_yaml(path, {"count": "nope"})
    with pytest.raises(ConfigurationError) as excinfo:
        load_typed_config(_Model, path)
    assert str(path) in str(excinfo.value)
