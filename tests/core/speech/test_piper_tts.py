from __future__ import annotations

import sys
from pathlib import Path

import pytest

from jarvis.core.config.voice_config import TextToSpeechConfig
from jarvis.core.exceptions import SpeechBackendUnavailableError
from jarvis.core.speech.piper_tts import PiperTextToSpeech


def test_construction_never_touches_disk_or_requires_backend(tmp_path: Path) -> None:
    config = TextToSpeechConfig(model_path=tmp_path / "does-not-exist.onnx")
    PiperTextToSpeech(config)  # must not raise


def test_missing_model_file_raises_clear_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("piper")
    config = TextToSpeechConfig(model_path=tmp_path / "missing.onnx")
    tts = PiperTextToSpeech(config)
    with pytest.raises(SpeechBackendUnavailableError, match="model file not found"):
        tts.synthesize("hello")


def test_missing_backend_raises_clear_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setitem(sys.modules, "piper", None)
    config = TextToSpeechConfig(model_path=tmp_path / "irrelevant.onnx")
    tts = PiperTextToSpeech(config)
    with pytest.raises(SpeechBackendUnavailableError, match="piper-tts is not installed"):
        tts.synthesize("hello")
