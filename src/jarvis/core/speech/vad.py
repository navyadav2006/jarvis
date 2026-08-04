"""WebRtcVoiceActivityDetector: a real VoiceActivityDetector
implementation (Phase 5's interface) backed by WebRTC's VAD, via the
`webrtcvad` package.

This is also this module's answer to "noise filtering": webrtcvad is
a classifier specifically trained to distinguish speech from
background noise, not a naive energy/volume threshold — audio that's
loud but not speech-shaped (fan noise, typing, music) is correctly
classified as non-speech. It's the same lightweight, purpose-built
library used by many real-time voice applications for exactly this
job; see docs/architecture.md's Phase 6 section for alternatives
considered.

webrtcvad is imported lazily inside `_ensure_vad()`, not at module
load time, for the same reason WhisperCppSpeechToText lazy-imports
pywhispercpp: constructing this class never requires the dependency
to be installed, only calling `is_speech()` does.
"""

from __future__ import annotations

from typing import Any

from jarvis.core.exceptions import SpeechBackendUnavailableError, SpeechError
from jarvis.core.voice.types import AudioChunk

_VALID_SAMPLE_RATES = (8000, 16000, 32000, 48000)
_VALID_FRAME_MS = (10, 20, 30)


class WebRtcVoiceActivityDetector:
    """Implements core.voice.ports.VoiceActivityDetector.

    webrtcvad requires each call to be exactly a 10, 20, or 30ms frame
    of mono 16-bit PCM at 8/16/32/48kHz — a stricter contract than
    AudioChunk's general shape, so is_speech() validates and raises
    SpeechError with a specific message rather than silently
    misbehaving on a chunk of the wrong size.
    """

    def __init__(self, *, aggressiveness: int = 2) -> None:
        if not 0 <= aggressiveness <= 3:
            raise ValueError(f"aggressiveness must be 0-3, got {aggressiveness}")
        self._aggressiveness = aggressiveness
        self._vad: Any = None

    def is_speech(self, chunk: AudioChunk) -> bool:
        if not chunk.data:
            return False

        if chunk.sample_rate not in _VALID_SAMPLE_RATES:
            raise SpeechError(
                f"WebRtcVoiceActivityDetector requires one of {_VALID_SAMPLE_RATES} Hz, "
                f"got {chunk.sample_rate}"
            )
        if chunk.channels != 1 or chunk.sample_width != 2:
            raise SpeechError(
                "WebRtcVoiceActivityDetector requires mono 16-bit PCM audio chunks, "
                f"got channels={chunk.channels} sample_width={chunk.sample_width}"
            )

        frame_ms = _frame_duration_ms(chunk)
        if round(frame_ms) not in _VALID_FRAME_MS:
            raise SpeechError(
                f"WebRtcVoiceActivityDetector requires 10/20/30ms frames, got {frame_ms:.1f}ms"
            )

        vad = self._ensure_vad()
        return vad.is_speech(chunk.data, chunk.sample_rate)

    def _ensure_vad(self) -> Any:
        if self._vad is not None:
            return self._vad

        try:
            import webrtcvad
        except ImportError as exc:
            raise SpeechBackendUnavailableError(
                "webrtcvad is not installed; install the 'voice' extra "
                "(pip install -e '.[voice]') to use WebRtcVoiceActivityDetector"
            ) from exc

        self._vad = webrtcvad.Vad(self._aggressiveness)
        return self._vad


def _frame_duration_ms(chunk: AudioChunk) -> float:
    num_samples = len(chunk.data) / chunk.sample_width / chunk.channels
    return (num_samples / chunk.sample_rate) * 1000.0
