"""Abstract interfaces for the voice pipeline's five stages:

    Microphone -> VoiceActivityDetector -> SpeechToText -> Assistant -> TextToSpeech -> AudioPlayer

(VoiceActivityDetector isn't in the user-facing pipeline diagram, but
it's what makes continuous/background listening possible at all:
without it, there is no way to know where one utterance ends and the
next begins in a continuous audio stream.)

This phase designs these interfaces only — no concrete implementation
backed by a real microphone, Whisper.cpp, or Piper exists yet (see
docs/architecture.md's Phase 5 section for why). Each Protocol ships
with a Null Object default (NullMicrophonePort, etc.), the same "safe,
fully-implemented default until a real backend exists" pattern used
for MemoryPort/AutomationPort in Phase 2 — these are not placeholders
for unfinished work, they're permanent, correct implementations of
"no backend configured."
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from jarvis.core.voice.types import AudioChunk, TranscriptionResult

logger = logging.getLogger(__name__)


@runtime_checkable
class MicrophonePort(Protocol):
    """Captures audio from an input device."""

    def start(self) -> None:
        """Begin capturing audio. Idempotent if already started."""
        ...

    def stop(self) -> None:
        """Stop capturing audio. Idempotent if already stopped."""
        ...

    def read(self, timeout: float | None = None) -> AudioChunk | None:
        """Return the next captured chunk, or None if none arrives within
        `timeout` seconds (or the stream has ended). `timeout=None` may
        block indefinitely — a background-listening pipeline is expected
        to call this from its own dedicated thread/task, never from
        whatever thread is also serving HTTP requests.
        """
        ...

    @property
    def is_active(self) -> bool:
        """Whether the microphone is currently capturing."""
        ...


@runtime_checkable
class WakeWordPort(Protocol):
    """Continuously fed short audio chunks; detects a configured wake
    word (e.g. "hey jarvis") within them.

    Unlike VoiceActivityDetector (a stateless yes/no classifier per
    chunk), a real wake-word model keeps a short rolling buffer
    internally across calls — a single 20-30ms chunk rarely contains
    enough audio to recognize a multi-syllable phrase. That buffering,
    and any per-model cooldown after a detection, is entirely the
    implementation's responsibility; callers just feed chunks as they
    arrive, in real time, the same way they feed VoiceActivityDetector.
    """

    def process(self, chunk: AudioChunk) -> str | None:
        """Feed one chunk of audio. Returns the name of the wake word
        model that fired, or None if none did (the overwhelmingly
        common outcome — this is called continuously while a pipeline
        waits for activation, so it must stay cheap).
        """
        ...

    def reset(self) -> None:
        """Clear internal buffering/cooldown state. A concrete
        VoicePipeline calls this when (re-)entering wake-word-waiting
        — e.g. after a conversation ends — so stale buffered audio
        from before doesn't influence the next detection.
        """
        ...


@runtime_checkable
class VoiceActivityDetector(Protocol):
    """Classifies whether a chunk of audio contains speech.

    Required for continuous and background listening, where there is
    no push-to-talk button to mark utterance boundaries: the pipeline
    needs some way to know when a spoken utterance starts and ends
    within an otherwise-continuous audio stream.
    """

    def is_speech(self, chunk: AudioChunk) -> bool: ...


@runtime_checkable
class SpeechToTextPort(Protocol):
    """Transcribes one complete audio utterance to text."""

    def transcribe(self, audio: AudioChunk) -> TranscriptionResult: ...


@runtime_checkable
class TextToSpeechPort(Protocol):
    """Synthesizes text to audio. Does not play it — see AudioPlayerPort."""

    def synthesize(self, text: str) -> AudioChunk: ...


@runtime_checkable
class AudioPlayerPort(Protocol):
    """Plays synthesized audio, and can be stopped mid-playback.

    `stop()` is what makes voice interruption (barge-in) possible: a
    concrete VoicePipeline calls it the moment its VoiceActivityDetector
    detects the user speaking while `is_playing` is True.

    Thread-safety contract: `stop()` and `is_playing` must be safe to
    call from a thread other than whichever one called `play()`. Since
    Phase 7, `core/speech/queue.py`'s SpeechQueue is exactly this case —
    it calls `play()` from its own worker thread while a caller (e.g. a
    future VoicePipeline.interrupt()) calls `stop()`/`skip()` from
    whatever thread it runs on.
    """

    def play(self, audio: AudioChunk) -> None:
        """Begin playback. Must not block until playback finishes —
        interrupt() needs to be able to call stop() while play() is
        still in progress elsewhere.
        """
        ...

    def stop(self) -> None:
        """Stop playback immediately. Safe to call when not playing."""
        ...

    @property
    def is_playing(self) -> bool: ...


@runtime_checkable
class AssistantHandler(Protocol):
    """The pipeline's 'Assistant' stage: transcribed text in, text to
    speak back out.

    Deliberately a plain callable Protocol rather than a direct
    dependency on Orchestrator: core/voice/ is core-layer infrastructure
    and must not depend on orchestrator/ (orchestrator depends on core,
    never the reverse — see docs/architecture.md's Phase 2 section on
    dependency direction). Whatever wires a real VoicePipeline together
    supplies something equivalent to
    ``lambda text, session_id: orchestrator.handle(Request(text=text,
    session_id=session_id, source="voice")).text or ""``.
    """

    def __call__(self, text: str, session_id: str) -> str: ...


class NullMicrophonePort:
    """No microphone backend configured. `read()` always returns None
    immediately rather than blocking for `timeout` — a real
    implementation would actually wait for audio.
    """

    def __init__(self) -> None:
        self._active = False

    def start(self) -> None:
        logger.debug("NullMicrophonePort.start() — no microphone backend configured")
        self._active = True

    def stop(self) -> None:
        self._active = False

    def read(self, timeout: float | None = None) -> AudioChunk | None:
        return None

    @property
    def is_active(self) -> bool:
        return self._active


class NullWakeWordPort:
    """No wake-word backend configured. process() never detects
    anything — a pipeline built on this default simply never activates
    via wake word (config.wake_word.enabled should be False in that
    case; see VoicePipeline.start()'s docstring).
    """

    def process(self, chunk: AudioChunk) -> str | None:
        return None

    def reset(self) -> None:
        pass


class NullVoiceActivityDetector:
    """No VAD backend configured. Never detects speech — a pipeline built
    on this default simply never segments an utterance, which is the
    correct behavior when there's no real detector to ask.
    """

    def is_speech(self, chunk: AudioChunk) -> bool:
        return False


class NullSpeechToTextPort:
    """No STT backend configured. Always returns an empty, zero-confidence
    transcription rather than raising, so a pipeline exercising this
    default degrades to "heard nothing" instead of crashing.
    """

    def transcribe(self, audio: AudioChunk) -> TranscriptionResult:
        logger.warning("NullSpeechToTextPort.transcribe() — no STT backend configured")
        return TranscriptionResult(text="", confidence=0.0, is_final=True)


class NullTextToSpeechPort:
    """No TTS backend configured. Returns silence (empty audio data)
    rather than raising.
    """

    def synthesize(self, text: str) -> AudioChunk:
        logger.warning(
            "NullTextToSpeechPort.synthesize(text=%r) — no TTS backend configured", text
        )
        return AudioChunk(data=b"", sample_rate=16000, channels=1)


class NullAudioPlayerPort:
    """No audio output backend configured. play() logs and does nothing;
    is_playing is always False, so interrupt() on a pipeline using this
    default is always a correct no-op.
    """

    def __init__(self) -> None:
        self._playing = False

    def play(self, audio: AudioChunk) -> None:
        logger.warning("NullAudioPlayerPort.play() — no audio output backend configured")

    def stop(self) -> None:
        self._playing = False

    @property
    def is_playing(self) -> bool:
        return self._playing
