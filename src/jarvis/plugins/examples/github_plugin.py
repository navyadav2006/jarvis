"""GitHubPlugin: a reference example plugin (Phase 18) — real, via
GitHub's REST API over `httpx`, lazily imported the same way
`core/cowork/http_transport.py`'s `HttpCoworkTransport` lazy-imports it
(the 'cowork' extra already covers httpx; no new dependency needed
here). Token and default repo come from `configure()`.
"""

from __future__ import annotations

from typing import Any

from jarvis.core.container import ServiceContainer
from jarvis.core.events import EventBus
from jarvis.core.exceptions import ExecutionBackendUnavailableError
from jarvis.orchestrator.capability_registry import CapabilityRegistry
from jarvis.orchestrator.models import CapabilityContext, CapabilityResult
from jarvis.plugins.base import PluginBase

_TIMEOUT_SECONDS = 15.0


class GitHubPlugin(PluginBase):
    name = "github"
    version = "1.0.0"
    description = "List open issues on a configured GitHub repository."
    required_permissions = ["network.http"]

    def configure(self, config: dict) -> None:
        self._token = config.get("token", "")
        self._repo = config.get("repo", "")

    def on_load(self, container: ServiceContainer, events: EventBus) -> None:
        if not hasattr(self, "_repo"):
            self.configure({})
        registry = container.resolve(CapabilityRegistry)
        registry.register(
            "github_list_issues",
            self._list_issues,
            patterns=[r"\blist (github )?issues\b", r"\bopen issues\b"],
            plugin=self.name,
            description="List open issues on the configured GitHub repository.",
        )

    def on_unload(self, container: ServiceContainer, events: EventBus) -> None:
        container.resolve(CapabilityRegistry).unregister_all_for_plugin(self.name)

    def _list_issues(self, context: CapabilityContext) -> CapabilityResult:
        if not self._repo:
            return CapabilityResult(text="GitHub is not configured (missing repo).")

        client = self._ensure_client()
        headers = {"Authorization": f"Bearer {self._token}"} if self._token else {}
        response = client.get(
            f"https://api.github.com/repos/{self._repo}/issues",
            headers=headers,
            timeout=_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        issues = response.json()
        if not issues:
            return CapabilityResult(text=f"No open issues on {self._repo}.")
        titles = "\n".join(f"#{issue['number']}: {issue['title']}" for issue in issues[:10])
        return CapabilityResult(text=titles)

    def _ensure_client(self) -> Any:
        try:
            import httpx
        except ImportError as exc:
            raise ExecutionBackendUnavailableError(
                "httpx is not installed; install the 'cowork' extra "
                "(pip install -e '.[cowork]') to use the GitHub plugin"
            ) from exc
        return httpx
