"""ObsidianPlugin: a reference example plugin (Phase 18) — the
simplest of the six, since it delegates entirely to the real
`VaultPort` (Phase 13) already in the container. No new dependency, no
new I/O of its own: this plugin is just a capability-registry facade
over `VaultService`.
"""

from __future__ import annotations

from jarvis.core.container import ServiceContainer
from jarvis.core.events import EventBus
from jarvis.core.vault.ports import VaultPort
from jarvis.orchestrator.capability_registry import CapabilityRegistry
from jarvis.orchestrator.models import CapabilityContext, CapabilityResult
from jarvis.plugins.base import PluginBase


class ObsidianPlugin(PluginBase):
    name = "obsidian"
    version = "1.0.0"
    description = "Create and read notes in the connected Obsidian vault."
    required_permissions = ["filesystem.read", "filesystem.write"]

    def on_load(self, container: ServiceContainer, events: EventBus) -> None:
        self._vault: VaultPort = container.resolve(VaultPort)
        registry = container.resolve(CapabilityRegistry)
        registry.register(
            "obsidian_create_note",
            self._create_note,
            patterns=[r"\bcreate a note\b", r"\bnew note\b"],
            plugin=self.name,
            description="Create a note in the Obsidian vault.",
        )

    def on_unload(self, container: ServiceContainer, events: EventBus) -> None:
        container.resolve(CapabilityRegistry).unregister_all_for_plugin(self.name)

    def _create_note(self, context: CapabilityContext) -> CapabilityResult:
        note = self._vault.write_note(
            f"Notes/{context.session.session_id}.md", context.request.text
        )
        return CapabilityResult(text=f"Created note {note.path!r}.")
