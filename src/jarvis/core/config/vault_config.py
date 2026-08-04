"""vault.yaml — Obsidian vault settings (Phase 13): folder layout,
version-history retention, and the auto-capture threshold for turning
conversations into structured knowledge.

`enabled: false` by default — main.bootstrap() only constructs the real
VaultService (core/vault/service.py) when this is true, same
cautious-rollout pattern as voice/cowork/memory. All paths are relative
to `vault_dir` (itself relative to the project root, matching
settings.yaml's `paths.vault_dir` — see path_guard.py's allowlist,
which already includes `vault` by default).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

VAULT_FILENAME = "vault.yaml"


class VaultConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    enabled: bool = False
    vault_dir: Path = Path("vault")

    # Folder organization — every path below is relative to vault_dir.
    daily_dir: Path = Path("Daily")
    projects_dir: Path = Path("Projects")
    conversations_dir: Path = Path("Conversations")
    devlogs_dir: Path = Path("Devlogs")
    # Where full-content snapshots go before a note is overwritten —
    # see core/vault/service.py's update_note()/rollback_note().
    versions_dir: Path = Path(".jarvis/versions")

    # A conversation must have at least this many turns before Jarvis
    # automatically writes a summary note for it — "every IMPORTANT
    # conversation," not literally every one.
    min_turns_for_auto_capture: int = Field(3, ge=1)
