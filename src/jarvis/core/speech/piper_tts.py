"""PiperTextToSpeech: a real TextToSpeechPort implementation (Phase 5's
interface) backed by Piper via the `piper-tts` Python package.

`piper-tts` (not a subprocess to Piper's CLI) was chosen for the same
reason `pywhispercpp` was chosen over a whisper.cpp subprocess in
Phase 6: the voice model loads once and stays resident in memory,
which repeated/real-time synthesis calls need — reloading a Piper
voice from disk before every utterance (as a fresh CLI subprocess
would) adds needless latency to every single response.

`piper-tts` is imported lazily inside `_ensure_voice()`, not at module
load time, for the same reason every other backend in this module is:
constructing this class — and importing jarvis.core.speech generally —
never requires it to be installed. Only the first real `synthesize()`
call does.

NOTE: `piper-tts`'s exact Python API was not verified against a locally
installed copy in this environment (no model file or package present
here to test against) — implemented against the documented 1.x shape
(`PiperVoice.load()` + `voice.synthesize()` yielding chunks with
`audio_int16_bytes`/`sample_rate`/`sample_channels`). Verify against
the installed version before relying on this in production; see
docs/architecture.md's Phase 7 section.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from jarvis.core.config.voice_config import TextToSpeechConfig
from jarvis.core.exceptions import SpeechBackendUnavailableError
from jarvis.core.voice.types import AudioChunk

logger = logging.getLogger(__name__)


class PiperTextToSpeech:
    """Implements core.voice.ports.TextToSpeechPort.

    Volume is deliberately NOT applied here — see SpeechQueue, which
    applies it at playback time via speech.audio.apply_gain() so
    changing volume never requires resynthesizing. `synthesize()`
    always returns audio at Piper's natural output level.
    """

    def __init__(self, config: TextToSpeechConfig) -> None:
        self._config = config
        self._voice: Any = None

    def synthesize(self, text: str) -> AudioChunk:
        voice = self._ensure_voice()

        parts: list[bytes] = []
        sample_rate: int | None = None
        for piper_chunk in voice.synthesize(text, syn_config=self._syn_config()):
            parts.append(piper_chunk.audio_int16_bytes)
            sample_rate = piper_chunk.sample_rate

        return AudioChunk(
            data=b"".join(parts),
            sample_rate=sample_rate or 22050,
            channels=1,
            sample_width=2,
        )

    def _syn_config(self) -> Any:
        from piper.config import SynthesisConfig

        # Piper's length_scale is the inverse of speaking rate: higher
        # values speak more slowly. speed=2.0 (twice as fast) -> 0.5;
        # speed=0.5 (half speed) -> 2.0.
        return SynthesisConfig(length_scale=1.0 / self._config.speed)

    def _ensure_voice(self) -> Any:
        if self._voice is not None:
            return self._voice

        try:
            from piper import PiperVoice
        except ImportError as exc:
            raise SpeechBackendUnavailableError(
                "piper-tts is not installed; install the 'voice' extra "
                "(pip install -e '.[voice]') to use PiperTextToSpeech"
            ) from exc

        model_path = Path(self._config.model_path)
        if not model_path.exists():
            raise SpeechBackendUnavailableError(
                f"Piper voice model file not found: {model_path} "
                "(download a Piper .onnx voice and update voice.yaml's tts.model_path)"
            )

        logger.info("Loading Piper voice %s", model_path)
        self._voice = PiperVoice.load(str(model_path))
        return self._voice
