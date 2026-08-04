from __future__ import annotations

import sys
from pathlib import Path

import pytest

from jarvis.core.config.voice_config import SpeechToTextConfig
from jarvis.core.exceptions import SpeechBackendUnavailableError
from jarvis.core.speech.whisper_cpp import WhisperCppSpeechToText
from jarvis.core.voice.types import AudioChunk

from .conftest import make_chunk


def test_construction_never_touches_disk_or_requires_backend(tmp_path: Path) -> None:
    # No model file exists at this path, and pywhispercpp may not be
    # installed — construction alone must not raise either way.
    config = SpeechToTextConfig(model_path=tmp_path / "does-not-exist.bin")
    WhisperCppSpeechToText(config)  # must not raise


def test_rejects_wrong_sample_rate() -> None:
    stt = WhisperCppSpeechToText(SpeechToTextConfig())
    chunk = make_chunk(0.5, sample_rate=44100)
    with pytest.raises(SpeechBackendUnavailableError):
        stt.transcribe(chunk)


def test_rejects_stereo() -> None:
    stt = WhisperCppSpeechToText(SpeechToTextConfig())
    chunk = AudioChunk(data=b"\x00\x00" * 100, sample_rate=16000, channels=2, sample_width=2)
    with pytest.raises(SpeechBackendUnavailableError):
        stt.transcribe(chunk)


def test_missing_model_file_raises_clear_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("pywhispercpp")
    config = SpeechToTextConfig(model_path=tmp_path / "missing.bin")
    stt = WhisperCppSpeechToText(config)
    chunk = make_chunk(0.5)
    with pytest.raises(SpeechBackendUnavailableError, match="model file not found"):
        stt.transcribe(chunk)


def test_missing_backend_raises_clear_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setitem(sys.modules, "pywhispercpp", None)
    monkeypatch.setitem(sys.modules, "pywhispercpp.model", None)
    config = SpeechToTextConfig(model_path=tmp_path / "irrelevant.bin")
    stt = WhisperCppSpeechToText(config)
    chunk = make_chunk(0.5)
    with pytest.raises(SpeechBackendUnavailableError, match="pywhispercpp is not installed"):
        stt.transcribe(chunk)
