"""plugins.yaml — which plugins load, and per-plugin configuration blobs.

`autoload`/`enabled`/`disabled` map directly onto
`PluginLoader.__init__`'s existing parameters (see main.bootstrap()).

The per-plugin `plugins` map (arbitrary config per plugin name) is
modeled and validated now but not yet consumed anywhere: `PluginBase`
has no `configure(dict)` lifecycle hook for a plugin to receive it.
Adding that hook now, before any plugin needs it, would mean guessing
its shape; the schema for *storing* per-plugin config is fixed here so
that when a plugin needing configuration is built, its config can go
straight into plugins.yaml without another config-system change.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

PLUGINS_FILENAME = "plugins.yaml"


class PluginEntryConfig(BaseModel):
    """Per-plugin settings, keyed by plugin name in PluginsConfig.plugins."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class PluginsConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    autoload: bool = True
    enabled: list[str] = Field(default_factory=list)
    disabled: list[str] = Field(default_factory=list)
    plugins: dict[str, PluginEntryConfig] = Field(default_factory=dict)
