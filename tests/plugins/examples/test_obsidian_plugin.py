from __future__ import annotations

from jarvis.core.vault.ports import NullVaultPort, VaultPort
from jarvis.orchestrator.capability_registry import CapabilityRegistry
from jarvis.plugins.examples.obsidian_plugin import ObsidianPlugin

from .conftest import make_container_and_events, make_context


class FakeVault(NullVaultPort):
    def __init__(self) -> None:
        self.written: list[tuple[str, str]] = []

    def write_note(self, path: str, body: str, *, frontmatter=None):
        self.written.append((path, body))
        from jarvis.core.vault.types import Note

        return Note(path=path, frontmatter=frontmatter or {}, body=body)


def test_on_load_registers_capability_and_resolves_vault() -> None:
    container, events = make_container_and_events()
    vault = FakeVault()
    container.register_instance(VaultPort, vault)
    registry = CapabilityRegistry()
    container.register_instance(CapabilityRegistry, registry)

    plugin = ObsidianPlugin()
    plugin.on_load(container, events)

    assert registry.get("obsidian_create_note") is not None


def test_create_note_writes_via_vault_port() -> None:
    container, events = make_container_and_events()
    vault = FakeVault()
    container.register_instance(VaultPort, vault)
    container.register_instance(CapabilityRegistry, CapabilityRegistry())

    plugin = ObsidianPlugin()
    plugin.on_load(container, events)

    context = make_context(text="remember to buy milk")
    result = plugin._create_note(context)

    assert vault.written == [("Notes/s1.md", "remember to buy milk")]
    assert "Notes/s1.md" in result.text


def test_on_unload_unregisters_capability() -> None:
    container, events = make_container_and_events()
    container.register_instance(VaultPort, FakeVault())
    registry = CapabilityRegistry()
    container.register_instance(CapabilityRegistry, registry)

    plugin = ObsidianPlugin()
    plugin.on_load(container, events)
    plugin.on_unload(container, events)

    assert registry.get("obsidian_create_note") is None
