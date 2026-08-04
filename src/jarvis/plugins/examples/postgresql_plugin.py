"""PostgresPlugin: a reference example plugin (Phase 18) — real, via
`subprocess` and the `psql` CLI (must be installed and on PATH;
connection string comes from `configure()`, the same
"configuration flows through plugins.yaml" pattern email_plugin.py
demonstrates). No new Python dependency (e.g. psycopg2) — consistent
with docker_plugin.py's CLI-over-SDK choice.
"""

from __future__ import annotations

import subprocess

from jarvis.core.container import ServiceContainer
from jarvis.core.events import EventBus
from jarvis.orchestrator.capability_registry import CapabilityRegistry
from jarvis.orchestrator.models import CapabilityContext, CapabilityResult
from jarvis.plugins.base import PluginBase

_TIMEOUT_SECONDS = 30.0


class PostgresPlugin(PluginBase):
    name = "postgresql"
    version = "1.0.0"
    description = "Run a read-only query against PostgreSQL via the `psql` CLI."
    required_permissions = ["terminal.run"]

    def configure(self, config: dict) -> None:
        self._connection_string = config.get("connection_string", "")

    def on_load(self, container: ServiceContainer, events: EventBus) -> None:
        if not hasattr(self, "_connection_string"):
            self._connection_string = ""
        registry = container.resolve(CapabilityRegistry)
        registry.register(
            "postgresql_query",
            self._run_query,
            patterns=[r"\bquery (the )?database\b", r"\brun (a )?sql\b"],
            plugin=self.name,
            description="Run a SQL query against the configured PostgreSQL database.",
        )

    def on_unload(self, container: ServiceContainer, events: EventBus) -> None:
        container.resolve(CapabilityRegistry).unregister_all_for_plugin(self.name)

    def _run_query(self, context: CapabilityContext) -> CapabilityResult:
        if not self._connection_string:
            return CapabilityResult(
                text="PostgreSQL is not configured (missing connection_string)."
            )

        query = context.request.metadata.get("query")
        if not query:
            return CapabilityResult(text="No SQL query given.")

        try:
            completed = subprocess.run(  # noqa: S603, S607
                ["psql", self._connection_string, "-c", query],
                capture_output=True,
                text=True,
                timeout=_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return CapabilityResult(text=f"Could not run psql: {exc}")

        if completed.returncode != 0:
            return CapabilityResult(text=f"Query failed: {completed.stderr.strip()}")
        return CapabilityResult(text=completed.stdout.strip())
