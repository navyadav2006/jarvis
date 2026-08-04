"""cowork.yaml — Claude Cowork integration settings (Phase 9).

`enabled: false` by default: no Cowork backend is wired into
main.py/the orchestrator yet (see core/cowork/'s module docstring).
The API key itself is never stored in YAML — `api_key_env_var` names
the environment variable HttpCoworkTransport reads it from at request
time, keeping secrets out of version control without needing the
config loader's env-override machinery (settings.yaml-only today).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

COWORK_FILENAME = "cowork.yaml"


class CoworkConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    enabled: bool = False

    # Placeholder — Claude Cowork's real base URL is not published in
    # this environment; update before enabling. See core/cowork/http_transport.py.
    base_url: str = "https://api.anthropic.com/cowork"
    endpoint_path: str = "/v1/tasks"
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
