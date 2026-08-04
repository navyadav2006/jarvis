from __future__ import annotations

import sys

import pytest

from jarvis.core.exceptions import SpeechBackendUnavailableError, SpeechError
from jarvis.core.speech.vad import WebRtcVoiceActivityDetector
from jarvis.core.voice.types import AudioChunk

from .conftest import make_chunk


def test_invalid_aggressiveness_rejected_at_construction() -> None:
    with pytest.raises(ValueError):
        WebRtcVoiceActivityDetector(aggressiveness=4)


def test_empty_chunk_is_never_speech() -> None:
    vad = WebRtcVoiceActivityDetector()
    chunk = AudioChunk(data=b"", sample_rate=16000, channels=1, sample_width=2)
    assert vad.is_speech(chunk) is False


def test_rejects_unsupported_sample_rate() -> None:
    vad = WebRtcVoiceActivityDetector()
    chunk = AudioChunk(data=b"\x00\x00" * 320, sample_rate=44100, channels=1, sample_width=2)
    with pytest.raises(SpeechError):
        vad.is_speech(chunk)


def test_rejects_stereo() -> None:
    vad = WebRtcVoiceActivityDetector()
    chunk = AudioChunk(data=b"\x00\x00" * 320, sample_rate=16000, channels=2, sample_width=2)
    with pytest.raises(SpeechError):
        vad.is_speech(chunk)


def test_rejects_non_10_20_30ms_frame() -> None:
    vad = WebRtcVoiceActivityDetector()
    # 16kHz mono 16-bit, 5ms worth of samples — not a valid webrtcvad frame size.
    chunk = make_chunk(0.005)
    with pytest.raises(SpeechError, match="10/20/30ms"):
        vad.is_speech(chunk)


def test_missing_backend_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "webrtcvad", None)  # forces ImportError on `import webrtcvad`
    vad = WebRtcVoiceActivityDetector()
    chunk = make_chunk(0.02)  # a valid 20ms frame
    with pytest.raises(SpeechBackendUnavailableError):
        vad.is_speech(chunk)


def test_real_webrtcvad_classifies_silence_as_not_speech() -> None:
    pytest.importorskip("webrtcvad")
    vad = WebRtcVoiceActivityDetector()
    silence = make_chunk(0.02, marker=b"\x00\x00")  # 20ms of pure silence
    assert vad.is_speech(silence) is False
