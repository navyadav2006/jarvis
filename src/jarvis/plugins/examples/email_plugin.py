"""EmailPlugin: a reference example plugin (Phase 18) — real, stdlib-only
(`smtplib`/`email.message`, no new dependency), and the clearest
demonstration of the `configure()` hook: SMTP host/port/credentials
come entirely from `plugins.yaml`'s `plugins.email.config` blob, not
hardcoded or read from a different config file.

Sending is lazy: `configure()` only stores settings; `on_load()` only
registers a capability. No SMTP connection is opened until a capability
handler actually runs — same "no I/O at load time" rule the other
examples follow, and the reason auto-loading these by default (see
examples/__init__.py) is safe.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from jarvis.core.container import ServiceContainer
from jarvis.core.events import EventBus
from jarvis.orchestrator.capability_registry import CapabilityRegistry
from jarvis.orchestrator.models import CapabilityContext, CapabilityResult
from jarvis.plugins.base import PluginBase


class EmailPlugin(PluginBase):
    name = "email"
    version = "1.0.0"
    description = "Send email via a configured SMTP server."
    required_permissions = ["email.send"]

    def configure(self, config: dict) -> None:
        self._smtp_host = config.get("smtp_host", "")
        self._smtp_port = int(config.get("smtp_port", 587))
        self._username = config.get("username", "")
        self._password = config.get("password", "")
        self._from_address = config.get("from_address", self._username)

    def on_load(self, container: ServiceContainer, events: EventBus) -> None:
        if not hasattr(self, "_smtp_host"):
            self.configure({})
        registry = container.resolve(CapabilityRegistry)
        registry.register(
            "email_send",
            self._send,
            patterns=[r"\bsend (an )?email\b", r"\bemail\b.*\bto\b"],
            plugin=self.name,
            description="Send an email via the configured SMTP server.",
        )

    def on_unload(self, container: ServiceContainer, events: EventBus) -> None:
        container.resolve(CapabilityRegistry).unregister_all_for_plugin(self.name)

    def _send(self, context: CapabilityContext) -> CapabilityResult:
        if not self._smtp_host:
            return CapabilityResult(text="Email is not configured (missing smtp_host).")

        to_address = context.request.metadata.get("to")
        if not to_address:
            return CapabilityResult(text="No recipient address given.")

        message = EmailMessage()
        message["From"] = self._from_address
        message["To"] = to_address
        message["Subject"] = context.request.metadata.get("subject", "Message from Jarvis")
        message.set_content(context.request.text)

        with smtplib.SMTP(self._smtp_host, self._smtp_port) as smtp:
            smtp.starttls()
            if self._username:
                smtp.login(self._username, self._password)
            smtp.send_message(message)

        return CapabilityResult(text=f"Email sent to {to_address}.")
