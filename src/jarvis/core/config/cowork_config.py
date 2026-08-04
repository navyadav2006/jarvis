"""cowork.yaml — Claude Cowork integration settings (Phase 9).

`enabled: false` by default: no Cowork backend is wired into
main.py/the orchestrator yet (see core/cowork/'s module docstring).
The API key itself is never stored in YAML — `api_key_env_var` names
the environment variable HttpCoworkTransport reads it from at request
time, keeping secrets out of version control without needing the
config loader's env-override machinery (settings.yaml-only today).

`base_url`/`endpoint_path` are vestigial as of the transport correction
below — `HttpCoworkTransport` now calls the real Claude Messages API
via the official `anthropic` SDK, which has its own fixed endpoint;
kept here only because `CoworkClient` still passes `endpoint_path`
into `CoworkTransport.post_json()` (unused by the real transport).

CORRECTION: earlier revisions of this file described `base_url` as "a
placeholder — Claude Cowork's real base URL is not published." That
premise was wrong: there is no separate "Claude Cowork" HTTP product
to look up a base URL for. Jarvis's Cowork collaborator now talks
directly to the real Claude API (`POST /v1/messages`), configured via
`model` below — see core/cowork/http_transport.py.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

COWORK_FILENAME = "cowork.yaml"


class CoworkConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    enabled: bool = False

    # The real Claude model Jarvis's Cowork collaborator talks to. See
    # docs/architecture.md's voice-wiring/Cowork-correction section for
    # why claude-opus-5 is the default (structured-outputs support,
    # Anthropic's own current-model recommendation).
    model: str = "claude-opus-5"

    # Vestigial — see module docstring above.
    base_url: str = "https://api.anthropic.com"
    endpoint_path: str = "/v1/messages"
    api_key_env_var: str = "COWORK_API_KEY"

    # Per-attempt wall-clock timeout for one HTTP call.
    timeout_seconds: float = Field(30.0, gt=0.0)

    # Total attempts is max_retries + 1 (the initial attempt isn't a "retry").
    max_retries: int = Field(2, ge=0)
    # Exponential backoff base: attempt N sleeps retry_backoff_seconds * 2**N.
    retry_backoff_seconds: float = Field(1.0, gt=0.0)

    # Routing threshold: Orchestrator only offers a request to Cowork
    # when no local capability matched (see core/cowork/'s module
    # docstring for the full local-vs-Cowork decision).
    min_confidence_for_local: float = Field(0.4, ge=0.0, le=1.0)
