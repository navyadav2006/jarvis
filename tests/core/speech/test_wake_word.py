from __future__ import annotations

import sys

import pytest

from jarvis.core.config.voice_config import WakeWordConfig
from jarvis.core.exceptions import SpeechBackendUnavailableError, SpeechError
from jarvis.core.speech.wake_word import OpenWakeWordDetector
from jarvis.core.voice.types import AudioChunk

from .conftest import make_chunk


class _FakeModel:
    """Stands in for openwakeword's Model: predict() returns pre-scripted
    {model_name: score} dicts, consumed in order.
    """

    def __init__(self, scripted_scores: list[dict[str, float]]) -> None:
        self._scripted = list(scripted_scores)
        self.reset_calls = 0

    def predict(self, samples: object) -> dict[str, float]:
        if self._scripted:
            return self._scripted.pop(0)
        return {}

    def reset(self) -> None:
        self.reset_calls += 1


def _wire_fake_model(detector: OpenWakeWordDetector, model: _FakeModel) -> None:
    # Set both the cached attribute reset() reads and the accessor
    # process() calls, so the fake behaves like a model that was
    # already lazily loaded.
    detector._model = model
    detector._ensure_model = lambda: model  # type: ignore[method-assign]


def test_construction_never_touches_disk_or_requires_backend() -> None:
    OpenWakeWordDetector(WakeWordConfig())  # must not raise


def test_missing_backend_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "openwakeword", None)
    detector = OpenWakeWordDetector(WakeWordConfig())
    with pytest.raises(SpeechBackendUnavailableError):
        detector.process(make_chunk(0.08))


def test_missing_custom_model_file_raises_clear_error() -> None:
    pytest.importorskip("openwakeword")
    detector = OpenWakeWordDetector(
        WakeWordConfig(models=["data/models/openwakeword/does_not_exist.onnx"])
    )
    with pytest.raises(SpeechBackendUnavailableError):
        detector.process(make_chunk(0.08))


def test_rejects_wrong_sample_format() -> None:
    detector = OpenWakeWordDetector(WakeWordConfig())
    chunk = AudioChunk(data=b"\x00\x00" * 100, sample_rate=44100, channels=1, sample_width=2)
    with pytest.raises(SpeechError):
        detector.process(chunk)


def test_empty_chunk_never_detects() -> None:
    detector = OpenWakeWordDetector(WakeWordConfig())
    chunk = AudioChunk(data=b"", sample_rate=16000, channels=1, sample_width=2)
    assert detector.process(chunk) is None


def test_score_above_threshold_returns_model_name() -> None:
    pytest.importorskip("numpy")
    detector = OpenWakeWordDetector(WakeWordConfig(threshold=0.5))
    _wire_fake_model(detector, _FakeModel([{"hey_jarvis": 0.9}]))
    assert detector.process(make_chunk(0.08)) == "hey_jarvis"


def test_score_below_threshold_returns_none() -> None:
    pytest.importorskip("numpy")
    detector = OpenWakeWordDetector(WakeWordConfig(threshold=0.5))
    _wire_fake_model(detector, _FakeModel([{"hey_jarvis": 0.2}]))
    assert detector.process(make_chunk(0.08)) is None


def test_cooldown_suppresses_immediate_retrigger() -> None:
    pytest.importorskip("numpy")
    detector = OpenWakeWordDetector(WakeWordConfig(threshold=0.5, cooldown_seconds=1.0))
    model = _FakeModel([{"hey_jarvis": 0.9}, {"hey_jarvis": 0.9}])
    _wire_fake_model(detector, model)

    assert detector.process(make_chunk(0.5)) == "hey_jarvis"
    assert detector.process(make_chunk(0.5)) is None  # still within the 1.0s cooldown


def test_cooldown_expires_after_enough_audio() -> None:
    pytest.importorskip("numpy")
    detector = OpenWakeWordDetector(WakeWordConfig(threshold=0.5, cooldown_seconds=1.0))
    model = _FakeModel([{"hey_jarvis": 0.9}] * 3)
    _wire_fake_model(detector, model)

    assert detector.process(make_chunk(0.5)) == "hey_jarvis"
    assert detector.process(make_chunk(0.4)) is None  # only 0.4s of cooldown consumed so far
    assert detector.process(make_chunk(0.7)) == "hey_jarvis"  # 1.1s since first detection


def test_reset_clears_cooldown_and_delegates_to_model() -> None:
    pytest.importorskip("numpy")
    detector = OpenWakeWordDetector(WakeWordConfig(threshold=0.5, cooldown_seconds=5.0))
    model = _FakeModel([{"hey_jarvis": 0.9}] * 3)
    _wire_fake_model(detector, model)

    assert detector.process(make_chunk(0.5)) == "hey_jarvis"
    assert detector.process(make_chunk(0.1)) is None  # still cooling down

    detector.reset()

    assert model.reset_calls == 1
    assert detector.process(make_chunk(0.1)) == "hey_jarvis"  # cooldown cleared by reset()


def test_multiple_models_are_scored_independently() -> None:
    pytest.importorskip("numpy")
    detector = OpenWakeWordDetector(
        WakeWordConfig(models=["hey_jarvis", "hey_computer"], threshold=0.5)
    )
    _wire_fake_model(detector, _FakeModel([{"hey_jarvis": 0.9, "hey_computer": 0.1}]))
    assert detector.process(make_chunk(0.08)) == "hey_jarvis"
