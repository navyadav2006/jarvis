from __future__ import annotations

from jarvis.core.config.plugins_config import PluginEntryConfig, PluginsConfig


def test_defaults() -> None:
    config = PluginsConfig()
    assert config.autoload is True
    assert config.enabled == []
    assert config.disabled == []
    assert config.plugins == {}


def test_per_plugin_entry_round_trips() -> None:
    config = PluginsConfig.model_validate(
        {
            "disabled": ["experimental"],
            "plugins": {"notes": {"enabled": True, "config": {"vault_subfolder": "Notes"}}},
        }
    )
    assert config.disabled == ["experimental"]
    entry = config.plugins["notes"]
    assert isinstance(entry, PluginEntryConfig)
    assert entry.config == {"vault_subfolder": "Notes"}
