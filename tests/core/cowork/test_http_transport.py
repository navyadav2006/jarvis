from __future__ import annotations

import json
import sys
import types
from typing import Any

import pytest

from jarvis.core.config.cowork_config import CoworkConfig
from jarvis.core.cowork.http_transport import HttpCoworkTransport
from jarvis.core.exceptions import CoworkUnavailableError


class _FakeTextBlock:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _FakeResponse:
    def __init__(self, *, content: list[Any], stop_reason: str = "end_turn") -> None:
        self.content = content
        self.stop_reason = stop_reason


class _FakeMessages:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> _FakeResponse:
        self.calls.append(kwargs)
        return self._response


class _FakeAnthropicClient:
    def __init__(self, *, api_key: str, response: _FakeResponse) -> None:
        self.api_key = api_key
        self.messages = _FakeMessages(response)
        self.with_options_calls: list[dict[str, Any]] = []

    def with_options(self, **kwargs: Any) -> "_FakeAnthropicClient":
        self.with_options_calls.append(kwargs)
        return self


class _FakeAPITimeoutError(Exception):
    pass


def _make_fake_anthropic_module(response: _FakeResponse) -> types.SimpleNamespace:
    holder: dict[str, _FakeAnthropicClient] = {}

    def _constructor(*, api_key: str) -> _FakeAnthropicClient:
        client = _FakeAnthropicClient(api_key=api_key, response=response)
        holder["client"] = client
        return client

    module = types.SimpleNamespace(Anthropic=_constructor, APITimeoutError=_FakeAPITimeoutError)
    module._holder = holder  # test-only escape hatch to inspect the constructed client
    return module


def _plan_response(*, action_type: str = "automation") -> _FakeResponse:
    parsed = {
        "summary": "Reading the file for you.",
        "steps": [
            {
                "step_id": 1,
                "description": "Read the notes file",
                "action_type": action_type,
                "automation_name": "filesystem.read" if action_type == "automation" else "",
                "automation_parameters_json": (
                    json.dumps({"path": "C:/notes.txt"}) if action_type == "automation" else "{}"
                ),
                "response_text": "" if action_type == "automation" else "Here you go.",
            }
        ],
    }
    return _FakeResponse(content=[_FakeTextBlock(json.dumps(parsed))])


def test_construction_never_touches_network_or_requires_backend() -> None:
    HttpCoworkTransport(CoworkConfig())  # must not raise


def test_missing_backend_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "anthropic", None)
    transport = HttpCoworkTransport(CoworkConfig())
    with pytest.raises(CoworkUnavailableError, match="anthropic"):
        transport.post_json("/v1/messages", {"task_id": "t1", "instruction": "hi"}, timeout=5.0)


def test_missing_api_key_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_module = _make_fake_anthropic_module(_plan_response())
    monkeypatch.setitem(sys.modules, "anthropic", fake_module)
    monkeypatch.delenv("COWORK_API_KEY", raising=False)
    transport = HttpCoworkTransport(CoworkConfig())
    with pytest.raises(CoworkUnavailableError, match="COWORK_API_KEY"):
        transport.post_json("/v1/messages", {"task_id": "t1", "instruction": "hi"}, timeout=5.0)


def test_post_json_sends_instruction_and_returns_automation_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_module = _make_fake_anthropic_module(_plan_response(action_type="automation"))
    monkeypatch.setitem(sys.modules, "anthropic", fake_module)
    monkeypatch.setenv("COWORK_API_KEY", "sk-test-key")

    transport = HttpCoworkTransport(CoworkConfig(model="claude-opus-5"))
    result = transport.post_json(
        "/v1/messages",
        {"task_id": "t1", "instruction": "read my notes", "context": {"note": "hi"}},
        timeout=12.0,
    )

    assert result["task_id"] == "t1"
    assert result["summary"] == "Reading the file for you."
    step = result["steps"][0]
    assert step["action_type"] == "automation"
    assert step["automation"] == {"name": "filesystem.read", "parameters": {"path": "C:/notes.txt"}}
    assert step["response_text"] is None

    client = fake_module._holder["client"]
    assert client.api_key == "sk-test-key"
    assert client.with_options_calls == [{"timeout": 12.0}]
    call = client.messages.calls[0]
    assert call["model"] == "claude-opus-5"
    assert call["messages"] == [{"role": "user", "content": "read my notes"}]
    assert "read my notes" not in call["system"]  # instruction isn't duplicated into system
    assert "hi" in call["system"]  # context was appended
    assert call["output_config"]["format"]["type"] == "json_schema"


def test_post_json_respond_step_carries_response_text_not_automation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_module = _make_fake_anthropic_module(_plan_response(action_type="respond"))
    monkeypatch.setitem(sys.modules, "anthropic", fake_module)
    monkeypatch.setenv("COWORK_API_KEY", "sk-test-key")

    transport = HttpCoworkTransport(CoworkConfig())
    result = transport.post_json(
        "/v1/messages", {"task_id": "t2", "instruction": "what time is it"}, timeout=5.0
    )

    step = result["steps"][0]
    assert step["action_type"] == "respond"
    assert step["automation"] is None
    assert step["response_text"] == "Here you go."


def test_post_json_handles_refusal_without_reading_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    refusal_response = _FakeResponse(content=[], stop_reason="refusal")
    fake_module = _make_fake_anthropic_module(refusal_response)
    monkeypatch.setitem(sys.modules, "anthropic", fake_module)
    monkeypatch.setenv("COWORK_API_KEY", "sk-test-key")

    transport = HttpCoworkTransport(CoworkConfig())
    result = transport.post_json(
        "/v1/messages", {"task_id": "t3", "instruction": "do something disallowed"}, timeout=5.0
    )

    assert result["task_id"] == "t3"
    assert result["steps"] == []


def test_post_json_converts_api_timeout_to_builtin_timeout_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_module = _make_fake_anthropic_module(_plan_response())

    def _raise_timeout(**kwargs: Any) -> None:
        raise fake_module.APITimeoutError("timed out")

    fake_module._holder = {}
    original_constructor = fake_module.Anthropic

    def _constructor(*, api_key: str) -> _FakeAnthropicClient:
        client = original_constructor(api_key=api_key)
        client.messages.create = _raise_timeout  # type: ignore[method-assign]
        return client

    fake_module.Anthropic = _constructor
    monkeypatch.setitem(sys.modules, "anthropic", fake_module)
    monkeypatch.setenv("COWORK_API_KEY", "sk-test-key")

    transport = HttpCoworkTransport(CoworkConfig())
    with pytest.raises(TimeoutError):
        transport.post_json("/v1/messages", {"task_id": "t4", "instruction": "hi"}, timeout=1.0)
