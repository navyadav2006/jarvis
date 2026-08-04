"""WhisperCppSpeechToText: a real SpeechToTextPort implementation
(Phase 5's interface) backed by whisper.cpp via the pywhispercpp
bindings.

pywhispercpp (not a subprocess to whisper.cpp's CLI or server) was
chosen so the model loads once and stays resident in memory — real-
time/repeated transcription calls need that; reloading a whisper.cpp
model from disk before every call (as a fresh CLI subprocess would)
costs well over a second each time. See docs/architecture.md's Phase 6
section for the alternatives considered and why.

pywhispercpp is imported lazily inside `_ensure_model()`, not at
module load time, so constructing this class — and importing
jarvis.core.speech generally — never requires it to be installed.
Only the first real `transcribe()` call does, and it fails with a
clear SpeechBackendUnavailableError (not an ImportError leaking out of
an unrelated stack) if it's missing.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from jarvis.core.config.voice_config import SpeechToTextConfig
from jarvis.core.exceptions import SpeechBackendUnavailableError
from jarvis.core.speech.audio import pcm16_bytes_to_float32
from jarvis.core.voice.types import AudioChunk, TranscriptionResult

logger = logging.getLogger(__name__)

_EXPECTED_SAMPLE_RATE = 16000


class WhisperCppSpeechToText:
    """Implements core.voice.ports.SpeechToTextPort."""

    def __init__(self, config: SpeechToTextConfig) -> None:
        self._config = config
        self._model: Any = None

    def transcribe(self, audio: AudioChunk) -> TranscriptionResult:
        if audio.sample_rate != _EXPECTED_SAMPLE_RATE or audio.channels != 1:
            raise SpeechBackendUnavailableError(
                f"whisper.cpp requires 16kHz mono audio, got "
                f"{audio.sample_rate}Hz/{audio.channels}ch — resample upstream "
                "(e.g. in the MicrophonePort implementation) before calling transcribe()"
            )

        model = self._ensure_model()
        samples = pcm16_bytes_to_float32(audio.data)

        auto_detect = self._config.language == "auto"
        language = None if auto_detect else self._config.language

        logger.debug(
            "Transcribing %.2fs of audio (language=%s)",
            len(samples) / _EXPECTED_SAMPLE_RATE,
            language or "auto",
        )
        segments = model.transcribe(samples, language=language)
        text = " ".join(segment.text.strip() for segment in segments).strip()
        detected_language = getattr(model, "language", None) if auto_detect else language

        return TranscriptionResult(
            text=text,
            confidence=None,  # whisper.cpp does not expose a calibrated per-segment score
            is_final=True,
            language=detected_language,
        )

    def _ensure_model(self) -> Any:
        if self._model is not None:
            return self._model

        try:
            from pywhispercpp.model import Model
        except ImportError as exc:
            raise SpeechBackendUnavailableError(
                "pywhispercpp is not installed; install the 'voice' extra "
                "(pip install -e '.[voice]') to use WhisperCppSpeechToText"
            ) from exc

        model_path = Path(self._config.model_path)
        if not model_path.exists():
            raise SpeechBackendUnavailableError(
                f"whisper.cpp model file not found: {model_path} "
                "(download a ggml model and update voice.yaml's stt.model_path)"
            )

        logger.info("Loading whisper.cpp model %s", model_path)
        self._model = Model(str(model_path))
        return self._model
