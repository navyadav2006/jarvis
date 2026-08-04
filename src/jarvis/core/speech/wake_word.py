"""OpenWakeWordDetector: a real WakeWordPort implementation (Phase 8's
interface) backed by openWakeWord.

openWakeWord's models are small ONNX (or optionally tflite) graphs
purpose-built to run continuously on a live microphone stream at a
tiny fraction of the CPU cost of running full speech-to-text — that's
what makes "always listening for a wake word, only run STT after one
fires" possible without pinning a CPU core. See docs/architecture.md's
Phase 8 section for the alternatives considered (a naive energy-
threshold keyword spotter, running whisper.cpp continuously) and why
openWakeWord was chosen.

openwakeword (and the numpy it needs to shape audio for it) is
imported lazily inside `_ensure_model()`, matching every other real
speech backend in this package (WhisperCppSpeechToText,
WebRtcVoiceActivityDetector, PiperTextToSpeech) — constructing this
class, and importing jarvis.core.speech generally, never requires it
to be installed.

Cooldown (config.wake_word.cooldown_seconds) is tracked in *audio*
seconds fed via process(), not wall-clock time — the same convention
streaming.py's StreamingTranscriber uses throughout, for the same
reason: it makes detection a pure, deterministic function of the audio
stream, fully testable with synthetic chunks instead of real-time
sleeps.

NOTE: openwakeword's exact Python API (Model(wakeword_models=...,
inference_framework=...), predict() returning a {model_name: score}
dict, reset()) was not verified against a locally installed copy in
this environment — implemented against its documented 0.x shape.
Verify against the installed version before relying on this in
production.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from jarvis.core.config.voice_config import WakeWordConfig
from jarvis.core.exceptions import SpeechBackendUnavailableError, SpeechError
from jarvis.core.speech.audio import chunk_duration_seconds
from jarvis.core.voice.types import AudioChunk

logger = logging.getLogger(__name__)

_EXPECTED_SAMPLE_RATE = 16000
_CUSTOM_MODEL_EXTENSIONS = (".onnx", ".tflite")


class OpenWakeWordDetector:
    """Implements core.voice.ports.WakeWordPort."""

    def __init__(self, config: WakeWordConfig) -> None:
        self._config = config
        self._model: Any = None
        self._cooldowns: dict[str, float] = {}  # model name -> audio seconds remaining

    def process(self, chunk: AudioChunk) -> str | None:
        if not chunk.data:
            return None
        if (
            chunk.sample_rate != _EXPECTED_SAMPLE_RATE
            or chunk.channels != 1
            or chunk.sample_width != 2
        ):
            raise SpeechError(
                "OpenWakeWordDetector requires 16kHz mono 16-bit PCM audio, got "
                f"{chunk.sample_rate}Hz/{chunk.channels}ch/{chunk.sample_width * 8}-bit"
            )

        self._tick_cooldowns(chunk_duration_seconds(chunk))

        model = self._ensure_model()
        samples = _pcm16_bytes_to_int16_array(chunk.data)
        scores = model.predict(samples)

        for name, score in scores.items():
            if score >= self._config.threshold and name not in self._cooldowns:
                logger.info("Wake word detected: %s (score=%.3f)", name, score)
                self._cooldowns[name] = self._config.cooldown_seconds
                return name
        return None

    def reset(self) -> None:
        self._cooldowns.clear()
        if self._model is not None:
            reset = getattr(self._model, "reset", None)
            if reset is not None:
                reset()

    def _tick_cooldowns(self, duration: float) -> None:
        for name in list(self._cooldowns):
            remaining = self._cooldowns[name] - duration
            if remaining <= 0:
                del self._cooldowns[name]
            else:
                self._cooldowns[name] = remaining

    def _ensure_model(self) -> Any:
        if self._model is not None:
            return self._model

        try:
            from openwakeword.model import Model
        except ImportError as exc:
            raise SpeechBackendUnavailableError(
                "openwakeword is not installed; install the 'voice' extra "
                "(pip install -e '.[voice]') to use OpenWakeWordDetector"
            ) from exc

        for entry in self._config.models:
            if entry.endswith(_CUSTOM_MODEL_EXTENSIONS) and not Path(entry).exists():
                raise SpeechBackendUnavailableError(
                    f"custom wake word model file not found: {entry} "
                    "(update voice.yaml's wake_word.models with a valid path)"
                )

        logger.info("Loading openWakeWord model(s): %s", self._config.models)
        self._model = Model(
            wakeword_models=list(self._config.models),
            inference_framework=self._config.inference_framework,
        )
        return self._model


def _pcm16_bytes_to_int16_array(data: bytes) -> Any:
    try:
        import numpy as np
    except ImportError as exc:
        raise SpeechBackendUnavailableError(
            "numpy is not installed; install the 'voice' extra "
            "(pip install -e '.[voice]') to use OpenWakeWordDetector"
        ) from exc
    return np.frombuffer(data, dtype=np.int16)
