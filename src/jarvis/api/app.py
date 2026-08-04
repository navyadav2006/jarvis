"""FastAPI application factory.

A factory function (rather than a module-level ``app = FastAPI()``) is
used so the app can be built with a specific, already-initialized
ServiceContainer — this keeps main.py's startup sequence as the single
place that decides *what* gets built, while this module only decides
*how* to expose it over HTTP. It also makes the app trivially testable:
tests can build a container with fakes/mocks and pass it in directly.
"""

from __future__ import annotations

import dataclasses

from fastapi import FastAPI
from pydantic import BaseModel

from jarvis import __version__
from jarvis.core.config import ConfigManager, Settings
from jarvis.core.container import ServiceContainer
from jarvis.core.plugin_loader import PluginLoader
from jarvis.orchestrator.models import Request as OrchestratorRequest
from jarvis.orchestrator.orchestrator import Orchestrator


class MessageIn(BaseModel):
    text: str
    session_id: str = "default"


class MessageOut(BaseModel):
    session_id: str
    intent: str
    handled: bool
    text: str | None
    data: dict


class HealthOut(BaseModel):
    status: str
    app: str
    version: str
    env: str
    plugins_loaded: list[str]


def create_app(container: ServiceContainer) -> FastAPI:
    settings = container.resolve(Settings)

    app = FastAPI(
        title=settings.app.name,
        version=__version__,
        debug=settings.app.debug,
    )
    app.state.container = container

    @app.get(
        "/health",
        response_model=HealthOut,
        summary="Liveness and readiness check",
        description=(
            "Reports process status, app name/version/env, and which plugins "
            "are currently active. Reads through ConfigManager (when "
            "registered) rather than the settings captured at app-creation "
            "time, so a live-reloaded settings.yaml is reflected here "
            "without restarting the server. Used by the Dockerfile/"
            "docker-compose.yml HEALTHCHECK — see docs/deployment.md."
        ),
    )
    def health() -> HealthOut:
        live_settings = (
            container.resolve(ConfigManager).settings if container.has(ConfigManager) else settings
        )

        loaded_plugins: list[str] = []
        if container.has(PluginLoader):
            loader = container.resolve(PluginLoader)
            loaded_plugins = sorted(loader.active.keys())

        return HealthOut(
            status="ok",
            app=live_settings.app.name,
            version=__version__,
            env=live_settings.app.env,
            plugins_loaded=loaded_plugins,
        )

    @app.get(
        "/config",
        summary="Dump the current value of every config domain",
        description=(
            "Diagnostic endpoint returning the live, in-memory value of every "
            "one of the 12 config domains (settings/permissions/voice/memory/"
            "plugins/filesystem/cowork/vault/execution/planning/security/"
            "workflow), reflecting any live reload. No authentication — see "
            "docs/architecture.md's Phase 2 'what's deliberately missing' "
            "list and docs/deployment.md's note on not exposing this route "
            "publicly. Returns {} if no ConfigManager is registered."
        ),
    )
    def get_config() -> dict:
        # Diagnostic endpoint: dumps the current, live value of every
        # config domain. No authentication yet — see docs/architecture.md's
        # Phase 2 "what's deliberately missing" list; this endpoint doesn't
        # widen that gap since /message already exposes no less.
        #
        # Built via dataclasses.fields() rather than one key per domain
        # spelled out by hand: this route drifted for 5 phases (Phase 9
        # through Phase 20) silently returning only its original 7
        # domains while ConfigManager grew to 12 — a stale test asserting
        # exactly those 7 keys is what let it go unnoticed (Phase 21).
        # Iterating LoadedConfig's own fields makes a new config domain
        # show up here automatically, the same way it's already
        # automatic in ConfigManager._files()/_load_all().
        if not container.has(ConfigManager):
            return {}
        snapshot = container.resolve(ConfigManager).snapshot()
        return {
            f.name: getattr(snapshot, f.name).model_dump(mode="json")
            for f in dataclasses.fields(snapshot)
        }

    @app.post(
        "/message",
        response_model=MessageOut,
        summary="Send one text message through the orchestrator",
        description=(
            "The single HTTP entry point into Orchestrator.handle() — "
            "intent recognition, capability dispatch, Cowork fallback, and "
            "memory recall/remember all happen here. This route does no "
            "handling itself; a future CLI or voice loop would call the "
            "same Orchestrator method directly instead of going through HTTP."
        ),
    )
    def post_message(payload: MessageIn) -> MessageOut:
        # The single HTTP entry point into the orchestrator. This route
        # does no intent handling itself — it only translates HTTP <-> the
        # orchestrator's own Request/Response types, exactly as a future
        # CLI or voice loop would.
        orchestrator = container.resolve(Orchestrator)
        response = orchestrator.handle(
            OrchestratorRequest(text=payload.text, session_id=payload.session_id, source="api")
        )
        return MessageOut(
            session_id=response.session_id,
            intent=response.intent_name,
            handled=response.handled,
            text=response.text,
            data=response.data,
        )

    return app
