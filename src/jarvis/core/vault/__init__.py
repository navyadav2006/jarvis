"""The vault module (Phase 13): Jarvis's connection to an Obsidian
vault, its permanent knowledge base.

`VaultService` (a real implementation over FilesystemPort, no new
dependency — PyYAML for frontmatter is already a base dependency) adds
Markdown/YAML-frontmatter note management, folder organization (daily
journals, project notes, conversation summaries, dev logs), automatic
`[[wikilink]]` backlinks, and version history with rollback on top of
Phase 4's filesystem module. See docs/architecture.md's Phase 13
section for the full design.
"""

from __future__ import annotations

from jarvis.core.vault.backlinks import add_backlink, extract_links
from jarvis.core.vault.frontmatter import parse_frontmatter, render_frontmatter
from jarvis.core.vault.ports import NullVaultPort, VaultPort
from jarvis.core.vault.service import VaultService
from jarvis.core.vault.types import Note, NoteVersion

__all__ = [
    "Note",
    "NoteVersion",
    "NullVaultPort",
    "VaultPort",
    "VaultService",
    "add_backlink",
    "extract_links",
    "parse_frontmatter",
    "render_frontmatter",
]
