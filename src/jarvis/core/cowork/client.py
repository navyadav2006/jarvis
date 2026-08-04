"""CoworkClient: request routing's counterpart on the outbound side —
turns a CoworkTaskRequest into an HTTP call (via whatever CoworkTransport
it's given), with timeout handling, retry logic, response parsing, and
diagnostics, all in one place so nothing downstream has to reimplement
any of it.

`CoworkTransport` is injected, not constructed here, so this entire
class — every requirement of this phase except the actual network call
— is fully testable against a fake transport with zero real HTTP calls
and zero real sleeping (the backoff sleep function is injectable too).
`HttpCoworkTransport` (http_transport.py) is the one real implementation,
and the only place `httpx` is imported.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from jarvis.core.config.cowork_config import CoworkConfig
from jarvis.core.cowork.models import CoworkDiagnostics, CoworkTaskRequest, CoworkTaskResponse
from jarvis.core.cowork.ports import CoworkTransport
from jarvis.core.events import EventBus
from jarvis.core.exceptions import (
    CoworkResponseError,
    CoworkTimeoutError,
    CoworkUnavailableError,
)

logger = logging.getLogger(__name__)


class CoworkClient:
    """Implements core.cowork.ports.CoworkClientPort."""

    def __init__(
        self,
        *,
        transport: CoworkTransport,
        config: CoworkConfig,
        events: EventBus | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._transport = transport
        self._config = config
        self._events = events
        self._sleep = sleep
        self._last_diagnostics: CoworkDiagnostics | None = None

    @property
    def last_diagnostics(self) -> CoworkDiagnostics | None:
        """The outcome of the most recently completed submit() call —
        the "diagnostics" requirement: attempts made, latency, and
        status, available without inspecting exceptions.
        """
        return self._last_diagnostics

    def submit(self, request: CoworkTaskRequest) -> CoworkTaskResponse:
        start = time.monotonic()
        self._publish("cowork.request_started", {"task_id": request.task_id})

        attempts = 0
        last_error: Exception | None = None
        max_attempts = self._config.max_retries + 1

        while attempts < max_attempts:
            attempts += 1
            try:
                raw = self._transport.post_json(
                    self._config.endpoint_path,
                    request.model_dump(mode="json"),
                    timeout=self._config.timeout_seconds,
                )
                response = self._parse_response(raw)
                self._record(request.task_id, attempts, start, "success")
                self._publish(
                    "cowork.request_succeeded",
                    {"task_id": request.task_id, "attempts": attempts},
                )
                return response
            except TimeoutError as exc:
                last_error = exc
                logger.warning(
                    "Cowork request %s timed out on attempt %d/%d",
                    request.task_id,
                    attempts,
                    max_attempts,
                )
                self._maybe_retry(request.task_id, attempts, max_attempts)
            except CoworkResponseError:
                raise  # malformed response is not retryable — retrying won't fix it
            except Exception as exc:  # transport-level failure (connection, HTTP status, etc.)
                last_error = exc
                logger.warning(
                    "Cowork request %s failed on attempt %d/%d: %s",
                    request.task_id,
                    attempts,
                    max_attempts,
                    exc,
                )
                self._maybe_retry(request.task_id, attempts, max_attempts)

        final_status = "timeout" if isinstance(last_error, TimeoutError) else "error"
        self._record(request.task_id, attempts, start, final_status, error=str(last_error))
        self._publish(
            "cowork.request_failed",
            {"task_id": request.task_id, "attempts": attempts, "error": str(last_error)},
        )
        if isinstance(last_error, TimeoutError):
            raise CoworkTimeoutError(
                f"Cowork request {request.task_id} timed out after {attempts} attempt(s)"
            ) from last_error
        raise CoworkUnavailableError(
            f"Cowork request {request.task_id} failed after {attempts} attempt(s): {last_error}"
        ) from last_error

    def _maybe_retry(self, task_id: str, attempts: int, max_attempts: int) -> None:
        if attempts >= max_attempts:
            return
        backoff = self._config.retry_backoff_seconds * (2 ** (attempts - 1))
        self._publish(
            "cowork.request_retrying",
            {"task_id": task_id, "attempt": attempts, "backoff_seconds": backoff},
        )
        self._sleep(backoff)

    def _parse_response(self, raw: dict[str, Any]) -> CoworkTaskResponse:
        try:
            return CoworkTaskResponse.model_validate(raw)
        except ValidationError as exc:
            raise CoworkResponseError(f"Malformed Cowork response: {exc}") from exc

    def _record(
        self,
        task_id: str,
        attempts: int,
        start: float,
        status: str,
        *,
        error: str | None = None,
    ) -> None:
        self._last_diagnostics = CoworkDiagnostics(
            task_id=task_id,
            attempts=attempts,
            latency_ms=(time.monotonic() - start) * 1000,
            status=status,  # type: ignore[arg-type]
            error=error,
        )
        logger.info("Cowork diagnostics: %s", self._last_diagnostics)

    def _publish(self, name: str, payload: dict[str, Any]) -> None:
        if self._events is not None:
            self._events.publish(name, payload, source="cowork_client")
