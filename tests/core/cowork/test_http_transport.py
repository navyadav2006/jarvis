from __future__ import annotations

import sys

import pytest

from jarvis.core.config.cowork_config import CoworkConfig
from jarvis.core.cowork.http_transport import HttpCoworkTransport
from jarvis.core.exceptions import CoworkUnavailableError


def test_construction_never_touches_network_or_requires_backend() -> None:
    HttpCoworkTransport(CoworkConfig())  # must not raise


def test_missing_backend_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "httpx", None)
    transport = HttpCoworkTransport(CoworkConfig())
    with pytest.raises(CoworkUnavailableError):
        transport.post_json("/v1/tasks", {}, timeout=5.0)


def test_missing_api_key_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("httpx")
    monkeypatch.delenv("COWORK_API_KEY", raising=False)
    transport = HttpCoworkTransport(CoworkConfig())
    with pytest.raises(CoworkUnavailableError, match="COWORK_API_KEY"):
        transport.post_json("/v1/tasks", {}, timeout=5.0)
