"""The global configuration system.

YAML files under `config/`, one typed pydantic model per file, loaded
and validated by `ConfigManager`:

    settings.yaml     -> Settings      (app/logging/paths/api/live-reload)
    permissions.yaml  -> PermissionsConfig
    voice.yaml        -> VoiceConfig
    memory.yaml       -> MemoryConfig
    plugins.yaml      -> PluginsConfig
    filesystem.yaml   -> FilesystemConfig
    cowork.yaml       -> CoworkConfig
    vault.yaml        -> VaultConfig
    execution.yaml    -> ExecutionConfig

`ConfigManager` is the reload-aware entry point everything else should
use (`container.resolve(ConfigManager).settings`, `.voice`, etc.).
`get_settings()`/`load_settings()` remain as one-shot, non-reload-aware
convenience functions for scripts and tests. See docs/architecture.md's
Phase 3 section for the full design rationale.
"""

from __future__ import annotations

from jarvis.core.config._paths import DEFAULT_CONFIG_DIR, PROJECT_ROOT
from jarvis.core.config.app_config import (
    ApiSettings,
    AppSettings,
    ConfigWatchSettings,
    LoggingSettings,
    PathsSettings,
    Settings,
    get_settings,
    load_settings,
)
from jarvis.core.config.cowork_config import CoworkConfig
from jarvis.core.config.execution_config import BrowserConfig, ExecutionConfig, TerminalConfig
from jarvis.core.config.filesystem_config import FilesystemConfig
from jarvis.core.config.loader import (
    deep_merge,
    env_overrides,
    load_typed_config,
    read_yaml_mapping,
)
from jarvis.core.config.manager import ConfigManager, LoadedConfig
from jarvis.core.config.memory_config import (
    LongTermMemoryConfig,
    MemoryConfig,
    SemanticMemoryConfig,
    ShortTermMemoryConfig,
    VectorIndexConfig,
)
from jarvis.core.config.permissions_config import PermissionRule, PermissionsConfig
from jarvis.core.config.planning_config import PlanningConfig
from jarvis.core.config.plugins_config import PluginEntryConfig, PluginsConfig
from jarvis.core.config.security_config import RateLimitConfig, SecurityConfig
from jarvis.core.config.vault_config import VaultConfig
from jarvis.core.config.voice_config import (
    ListeningConfig,
    ListeningMode,
    SpeechQueueConfig,
    SpeechToTextConfig,
    StreamingConfig,
    TextToSpeechConfig,
    VoiceConfig,
    WakeWordConfig,
)
from jarvis.core.config.workflow_config import WorkflowConfig

__all__ = [
    "PROJECT_ROOT",
    "DEFAULT_CONFIG_DIR",
    "ApiSettings",
    "AppSettings",
    "ConfigWatchSettings",
    "LoggingSettings",
    "PathsSettings",
    "Settings",
    "get_settings",
    "load_settings",
    "CoworkConfig",
    "FilesystemConfig",
    "deep_merge",
    "env_overrides",
    "load_typed_config",
    "read_yaml_mapping",
    "ConfigManager",
    "LoadedConfig",
    "LongTermMemoryConfig",
    "MemoryConfig",
    "SemanticMemoryConfig",
    "ShortTermMemoryConfig",
    "VectorIndexConfig",
    "PermissionRule",
    "PermissionsConfig",
    "PluginEntryConfig",
    "PluginsConfig",
    "ListeningConfig",
    "ListeningMode",
    "SpeechQueueConfig",
    "SpeechToTextConfig",
    "StreamingConfig",
    "TextToSpeechConfig",
    "VoiceConfig",
    "WakeWordConfig",
    "VaultConfig",
    "ExecutionConfig",
    "TerminalConfig",
    "BrowserConfig",
    "PlanningConfig",
    "SecurityConfig",
    "RateLimitConfig",
    "WorkflowConfig",
]
