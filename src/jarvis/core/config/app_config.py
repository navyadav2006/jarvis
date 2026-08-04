"""settings.yaml — general application settings: identity, logging,
filesystem paths, the HTTP API bind address, and the config system's
own live-reload behavior.

This is the only one of the five config domains with environment-
variable override support (`APP__NAME=...`, `LOGGING__LEVEL=...`, plus
`.env`, both handled by loader.env_overrides()) — matching Phase 1's
original behavior, since these are the values most likely to differ
per-deployment (dev vs prod, CI, a user's machine). The other four
domains (permissions, voice, memory, plugins) are meant to be edited
directly and are not env-overridable; see manager.py for where each
domain's override policy is decided.

Every model here is frozen: a Settings object is a value, not
something code mutates in place. When settings.yaml changes on disk,
ConfigManager builds a brand-new Settings and replaces the old one
wholesale — nothing ever does `settings.app.debug = True`.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from jarvis.core.config._paths import DEFAULT_CONFIG_DIR, PROJECT_ROOT
from jarvis.core.config.loader import env_overrides, load_typed_config

SETTINGS_FILENAME = "settings.yaml"


class AppSettings(BaseModel):
    """Identity and run-mode of the application itself."""

    model_config = ConfigDict(frozen=True)

    name: str = "Jarvis"
    env: str = "development"
    debug: bool = False


class LoggingSettings(BaseModel):
    """Everything logging_setup.py needs to configure Python logging."""

    model_config = ConfigDict(frozen=True)

    level: str = "INFO"
    format: str = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    date_format: str = "%Y-%m-%d %H:%M:%S"
    dir: Path = Path("logs")
    file_name: str = "jarvis.log"
    max_bytes: int = 10_000_000
    backup_count: int = 5
    console: bool = True


class PathsSettings(BaseModel):
    """Local-first data locations. All relative paths resolve from PROJECT_ROOT."""

    model_config = ConfigDict(frozen=True)

    data_dir: Path = Path("data")
    plugins_dir: Path = Path("plugins")
    vault_dir: Path = Path("vault")
    prompts_dir: Path = Path("prompts")

    def resolved(self, root: Path = PROJECT_ROOT) -> PathsSettings:
        """Return a copy with every path made absolute against ``root``."""
        return PathsSettings(
            data_dir=root / self.data_dir,
            plugins_dir=root / self.plugins_dir,
            vault_dir=root / self.vault_dir,
            prompts_dir=root / self.prompts_dir,
        )


class ApiSettings(BaseModel):
    """Bind address for the FastAPI startup server."""

    model_config = ConfigDict(frozen=True)

    host: str = "127.0.0.1"
    port: int = 8756


class ConfigWatchSettings(BaseModel):
    """Controls ConfigManager's optional background file-watching (live reload)."""

    model_config = ConfigDict(frozen=True)

    live_reload: bool = True
    poll_interval_seconds: float = Field(2.0, gt=0.0)


class Settings(BaseModel):
    """Root settings object for the settings.yaml domain."""

    model_config = ConfigDict(frozen=True)

    app: AppSettings = Field(default_factory=AppSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    paths: PathsSettings = Field(default_factory=PathsSettings)
    api: ApiSettings = Field(default_factory=ApiSettings)
    config: ConfigWatchSettings = Field(default_factory=ConfigWatchSettings)


def load_settings(path: Path = DEFAULT_CONFIG_DIR / SETTINGS_FILENAME) -> Settings:
    """Load, env-override, and validate settings.yaml. Raises ConfigurationError."""
    return load_typed_config(Settings, path, overrides=env_overrides())


def get_settings(path: Path = DEFAULT_CONFIG_DIR / SETTINGS_FILENAME) -> Settings:
    """One-shot convenience for callers that just want current settings.yaml
    right now (simple scripts, tests). Not reload-aware and not cached —
    main.py uses ConfigManager, which is, for anything that needs to
    observe live changes.
    """
    return load_settings(path)
