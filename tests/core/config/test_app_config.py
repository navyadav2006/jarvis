from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from jarvis.core.config.app_config import PathsSettings, Settings
from jarvis.core.config.loader import env_overrides, load_typed_config
from jarvis.core.exceptions import ConfigurationError

from .conftest import write_yaml


def test_settings_defaults_when_file_missing(tmp_path: Path) -> None:
    settings = load_typed_config(Settings, tmp_path / "settings.yaml")
    assert settings.app.name == "Jarvis"
    assert settings.logging.level == "INFO"
    assert settings.config.live_reload is True


def test_settings_reads_yaml_values(tmp_path: Path) -> None:
    path = tmp_path / "settings.yaml"
    write_yaml(path, {"app": {"name": "Custom"}, "logging": {"level": "WARNING"}})
    settings = load_typed_config(Settings, path)
    assert settings.app.name == "Custom"
    assert settings.logging.level == "WARNING"


def test_settings_env_override_wins_over_yaml(tmp_path: Path) -> None:
    path = tmp_path / "settings.yaml"
    write_yaml(path, {"logging": {"level": "INFO"}})
    overrides = env_overrides(environ={"LOGGING__LEVEL": "DEBUG"})
    settings = load_typed_config(Settings, path, overrides=overrides)
    assert settings.logging.level == "DEBUG"


def test_settings_is_frozen() -> None:
    settings = Settings()
    with pytest.raises(ValidationError):
        settings.app = settings.app  # type: ignore[misc]


def test_settings_invalid_field_raises_configuration_error(tmp_path: Path) -> None:
    path = tmp_path / "settings.yaml"
    write_yaml(path, {"api": {"port": "not-a-port"}})
    with pytest.raises(ConfigurationError):
        load_typed_config(Settings, path)


def test_paths_resolved_makes_paths_absolute(tmp_path: Path) -> None:
    paths = PathsSettings(
        data_dir=Path("data"),
        plugins_dir=Path("plugins"),
        vault_dir=Path("vault"),
        prompts_dir=Path("prompts"),
    )
    resolved = paths.resolved(root=tmp_path)
    assert resolved.data_dir == tmp_path / "data"
    assert resolved.data_dir.is_absolute()
    assert resolved.prompts_dir == tmp_path / "prompts"


def test_paths_prompts_dir_defaults_to_prompts() -> None:
    assert PathsSettings().prompts_dir == Path("prompts")
