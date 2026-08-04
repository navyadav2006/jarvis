"""HttpCoworkTransport: the one real CoworkTransport implementation,
POSTing JSON to `config.base_url + path` over HTTPS via `httpx`.

NOTE: Claude Cowork's real HTTP API contract (auth header format, exact
request/response envelope) is not published/verified in this
environment — implemented against a generic bearer-token REST-JSON
shape, the same "documented shape, not verified against a real install"
caveat every other real backend in this project carries (see
core/speech/piper_tts.py, core/speech/wake_word.py). Verify against
Cowork's actual API docs before enabling this in production.

`httpx` is imported lazily, inside `_client()`, matching every other
optional third-party dependency in this project — constructing this
class, and importing jarvis.core.cowork generally, never requires it
to be installed. The API key is read from the environment (not passed
at construction) so it's never accidentally captured in a config
snapshot or log line.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from jarvis.core.config.cowork_config import CoworkConfig
from jarvis.core.exceptions import CoworkUnavailableError

logger = logging.getLogger(__name__)


class HttpCoworkTransport:
    """Implements core.cowork.ports.CoworkTransport."""

    def __init__(self, config: CoworkConfig) -> None:
        self._config = config
        self._client: Any = None

    def post_json(self, path: str, payload: dict[str, Any], *, timeout: float) -> dict[str, Any]:
        client = self._ensure_client()  # raises CoworkUnavailableError if httpx is missing
        import httpx

        try:
            response = client.post(self._config.base_url + path, json=payload, timeout=timeout)
        except httpx.TimeoutException as exc:
            # CoworkTransport's contract requires the built-in TimeoutError,
            # not httpx's own exception type, so CoworkClient's retry loop
            # doesn't need to know which HTTP library is behind the port.
            raise TimeoutError(str(exc)) from exc
        response.raise_for_status()
        return response.json()

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client

        try:
            import httpx
        except ImportError as exc:
            raise CoworkUnavailableError(
                "httpx is not installed; install the 'cowork' extra "
                "(pip install -e '.[cowork]') to use HttpCoworkTransport"
            ) from exc

        api_key = os.environ.get(self._config.api_key_env_var)
        if not api_key:
            raise CoworkUnavailableError(
                f"environment variable {self._config.api_key_env_var} is not set "
                "(update cowork.yaml's api_key_env_var, or set it in the environment)"
            )

        logger.info("Creating Cowork HTTP client for %s", self._config.base_url)
        self._client = httpx.Client(headers={"Authorization": f"Bearer {api_key}"})
        return self._client
