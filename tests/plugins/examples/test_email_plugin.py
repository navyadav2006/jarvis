from __future__ import annotations

from jarvis.orchestrator.capability_registry import CapabilityRegistry
from jarvis.plugins.examples.email_plugin import EmailPlugin

from .conftest import make_container_and_events, make_context


def test_configure_reads_smtp_settings() -> None:
    plugin = EmailPlugin()
    plugin.configure(
        {
            "smtp_host": "smtp.example.com",
            "smtp_port": 25,
            "username": "me@example.com",
            "password": "secret",
        }
    )
    assert plugin._smtp_host == "smtp.example.com"
    assert plugin._smtp_port == 25
    assert plugin._from_address == "me@example.com"


def test_on_load_registers_capability_without_configure() -> None:
    container, events = make_container_and_events()
    registry = CapabilityRegistry()
    container.register_instance(CapabilityRegistry, registry)

    plugin = EmailPlugin()
    plugin.on_load(container, events)  # configure() never called explicitly

    assert registry.get("email_send") is not None
    assert plugin._smtp_host == ""


def test_send_without_configuration_reports_clearly() -> None:
    plugin = EmailPlugin()
    plugin.configure({})

    result = plugin._send(make_context(metadata={"to": "you@example.com"}))

    assert "not configured" in result.text


def test_send_without_recipient_reports_clearly() -> None:
    plugin = EmailPlugin()
    plugin.configure({"smtp_host": "smtp.example.com"})

    result = plugin._send(make_context(metadata={}))

    assert "No recipient" in result.text
