"""DockerPlugin: a reference example plugin (Phase 18) — real, via
`subprocess` and the `docker` CLI (must be installed and on PATH; no
new Python dependency, the same choice
`core/execution/application.py`'s `ProcessApplicationManager` made for
launching/closing applications).
"""

from __future__ import annotations

import subprocess

from jarvis.core.container import ServiceContainer
from jarvis.core.events import EventBus
from jarvis.orchestrator.capability_registry import CapabilityRegistry
from jarvis.orchestrator.models import CapabilityContext, CapabilityResult
from jarvis.plugins.base import PluginBase

_TIMEOUT_SECONDS = 30.0


class DockerPlugin(PluginBase):
    name = "docker"
    version = "1.0.0"
    description = "List running Docker containers via the `docker` CLI."
    required_permissions = ["terminal.run"]

    def on_load(self, container: ServiceContainer, events: EventBus) -> None:
        registry = container.resolve(CapabilityRegistry)
        registry.register(
            "docker_list_containers",
            self._list_containers,
            patterns=[r"\blist (docker )?containers\b", r"\bdocker ps\b"],
            plugin=self.name,
            description="List running Docker containers.",
        )

    def on_unload(self, container: ServiceContainer, events: EventBus) -> None:
        container.resolve(CapabilityRegistry).unregister_all_for_plugin(self.name)

    def _list_containers(self, context: CapabilityContext) -> CapabilityResult:
        try:
            completed = subprocess.run(  # noqa: S603, S607
                ["docker", "ps", "--format", "{{.Names}}\t{{.Status}}"],
                capture_output=True,
                text=True,
                timeout=_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return CapabilityResult(text=f"Could not run docker: {exc}")

        if completed.returncode != 0:
            return CapabilityResult(text=f"docker ps failed: {completed.stderr.strip()}")
        if not completed.stdout.strip():
            return CapabilityResult(text="No containers are running.")
        return CapabilityResult(text=completed.stdout.strip())
