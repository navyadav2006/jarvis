from __future__ import annotations

from typing import Any

import pytest

from jarvis.core.config.cowork_config import CoworkConfig
from jarvis.core.cowork.client import CoworkClient
from jarvis.core.cowork.models import CoworkTaskRequest
from jarvis.core.cowork.ports import CoworkClientPort, NullCoworkClientPort
from jarvis.core.events import EventBus
from jarvis.core.exceptions import (
    CoworkResponseError,
    CoworkTimeoutError,
    CoworkUnavailableError,
)

VALID_RESPONSE = {
    "task_id": "t1",
    "summary": "did the thing",
    "steps": [
        {
            "step_id": 1,
            "description": "click the button",
            "action_type": "automation",
            "automation": {"name": "click", "parameters": {"x": 1, "y": 2}},
        }
    ],
}


class FakeTransport:
    """Scripted CoworkTransport: raises/returns pre-scripted outcomes,
    one per call, consumed in order.
    """

    def __init__(self, outcomes: list[Any]) -> None:
        self._outcomes = list(outcomes)
        self.calls: list[tuple[str, dict, float]] = []

    def post_json(self, path: str, payload: dict, *, timeout: float) -> dict:
        self.calls.append((path, payload, timeout))
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _config(**overrides: Any) -> CoworkConfig:
    return CoworkConfig(**{"max_retries": 2, "retry_backoff_seconds": 0.01, **overrides})


def _request() -> CoworkTaskRequest:
    return CoworkTaskRequest(session_id="s1", instruction="do the thing")


def test_client_satisfies_port_protocol() -> None:
    transport = FakeTransport([VALID_RESPONSE])
    assert isinstance(CoworkClient(transport=transport, config=_config()), CoworkClientPort)


def test_successful_submit_parses_response() -> None:
    transport = FakeTransport([VALID_RESPONSE])
    client = CoworkClient(transport=transport, config=_config())

    response = client.submit(_request())

    assert response.summary == "did the thing"
    assert len(response.steps) == 1
    assert response.steps[0].automation.name == "click"


def test_request_payload_sent_to_transport_matches_model() -> None:
    transport = FakeTransport([VALID_RESPONSE])
    client = CoworkClient(transport=transport, config=_config())
    request = _request()

    client.submit(request)

    path, payload, timeout = transport.calls[0]
    assert path == _config().endpoint_path
    assert payload["session_id"] == "s1"
    assert payload["instruction"] == "do the thing"
    assert timeout == _config().timeout_seconds


def test_malformed_response_raises_response_error_without_retrying() -> None:
    transport = FakeTransport([{"not": "a valid response"}])
    client = CoworkClient(transport=transport, config=_config())

    with pytest.raises(CoworkResponseError):
        client.submit(_request())

    assert len(transport.calls) == 1  # not retried — malformed data won't fix itself


def test_transient_failure_is_retried_then_succeeds() -> None:
    transport = FakeTransport([ConnectionError("boom"), VALID_RESPONSE])
    sleeps: list[float] = []
    client = CoworkClient(transport=transport, config=_config(), sleep=sleeps.append)

    response = client.submit(_request())

    assert response.summary == "did the thing"
    assert len(transport.calls) == 2
    assert sleeps == [0.01]  # one retry, backoff = retry_backoff_seconds * 2**0


def test_exhausting_retries_raises_unavailable_error() -> None:
    transport = FakeTransport([ConnectionError("a"), ConnectionError("b"), ConnectionError("c")])
    client = CoworkClient(transport=transport, config=_config(max_retries=2), sleep=lambda s: None)

    with pytest.raises(CoworkUnavailableError):
        client.submit(_request())

    assert len(transport.calls) == 3  # initial attempt + 2 retries


def test_timeout_is_retried_then_raises_timeout_error() -> None:
    transport = FakeTransport([TimeoutError("slow"), TimeoutError("slow")])
    client = CoworkClient(transport=transport, config=_config(max_retries=1), sleep=lambda s: None)

    with pytest.raises(CoworkTimeoutError):
        client.submit(_request())

    assert len(transport.calls) == 2


def test_backoff_is_exponential() -> None:
    transport = FakeTransport([ConnectionError("a"), ConnectionError("b"), VALID_RESPONSE])
    sleeps: list[float] = []
    client = CoworkClient(
        transport=transport,
        config=_config(max_retries=2, retry_backoff_seconds=1.0),
        sleep=sleeps.append,
    )

    client.submit(_request())

    assert sleeps == [1.0, 2.0]  # 1.0 * 2**0, then 1.0 * 2**1


def test_diagnostics_recorded_on_success() -> None:
    transport = FakeTransport([VALID_RESPONSE])
    client = CoworkClient(transport=transport, config=_config())

    client.submit(_request())

    diagnostics = client.last_diagnostics
    assert diagnostics is not None
    assert diagnostics.status == "success"
    assert diagnostics.attempts == 1


def test_diagnostics_recorded_on_failure() -> None:
    transport = FakeTransport([ConnectionError("a")] * 3)
    client = CoworkClient(transport=transport, config=_config(max_retries=2), sleep=lambda s: None)

    with pytest.raises(CoworkUnavailableError):
        client.submit(_request())

    diagnostics = client.last_diagnostics
    assert diagnostics is not None
    assert diagnostics.status == "error"
    assert diagnostics.attempts == 3


def test_events_published_for_lifecycle() -> None:
    transport = FakeTransport([ConnectionError("a"), VALID_RESPONSE])
    events = EventBus()
    received: list[str] = []
    for name in (
        "cowork.request_started",
        "cowork.request_retrying",
        "cowork.request_succeeded",
    ):
        events.subscribe(name, lambda e, n=name: received.append(n))

    client = CoworkClient(
        transport=transport, config=_config(), events=events, sleep=lambda s: None
    )
    client.submit(_request())

    assert received == [
        "cowork.request_started",
        "cowork.request_retrying",
        "cowork.request_succeeded",
    ]


def test_null_client_returns_empty_plan() -> None:
    response = NullCoworkClientPort().submit(_request())
    assert response.steps == []
    assert isinstance(response.summary, str)
