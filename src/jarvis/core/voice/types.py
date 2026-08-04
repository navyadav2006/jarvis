"""Domain types shared by every voice port and by VoicePipeline.

Kept dependency-free of any concrete audio/STT/TTS library — everything
here is a plain data type or enum, the same "ports depend on plain
types, plain types depend on nothing" shape used by
orchestrator/models.py and core/filesystem/port.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


@dataclass(frozen=True)
class AudioChunk:
    """Raw audio, either captured from a microphone or synthesized by TTS.

    PCM parameters (sample_rate/channels/sample_width) travel with the
    data rather than being assumed, since a real microphone backend and
    a real TTS backend will not necessarily agree on a format — a
    concrete VoicePipeline is responsible for resampling/converting if
    the two differ.
    """

    data: bytes
    sample_rate: int
    channels: int = 1
    sample_width: int = 2  # bytes per sample; 2 = 16-bit PCM
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class TranscriptionResult:
    """What SpeechToTextPort.transcribe() returns for one utterance.

    `is_final` and `confidence` were modeled ahead of any real STT
    backend (Phase 5) so a streaming-capable one could be a drop-in
    SpeechToTextPort without changing this type. As of Phase 6,
    `is_final=False` is genuinely used: SpeechToTextPort itself is
    still single-shot (whisper.cpp transcribes one complete buffer per
    call), but core/speech/streaming.py's StreamingTranscriber calls it
    repeatedly on a growing buffer to produce low-latency partial
    results, then a final one once a pause is detected.
    """

    text: str
    confidence: float | None = None
    is_final: bool = True
    language: str | None = None


class VoiceState(StrEnum):
    """VoicePipeline's lifecycle state. A concrete implementation is
    expected to only move between these via `VoicePipeline._set_state()`,
    so every transition is logged in one place.
    """

    IDLE = "idle"
    # Added in Phase 8: entered instead of LISTENING when
    # config.wake_word.enabled — audio is fed to WakeWordPort.process()
    # rather than VoiceActivityDetector/SpeechToTextPort until a wake
    # word fires, which is what keeps continuous listening cheap.
    WAITING_FOR_WAKE_WORD = "waiting_for_wake_word"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"


class VoiceEvents:
    """EventBus event names every VoicePipeline implementation publishes.

    Centralized as a namespace of constants (not an Enum, since
    EventBus.publish() takes a plain string) so a concrete
    implementation and anything subscribing to it agree on exact
    spelling without either importing the other's literals.
    """

    LISTENING_STARTED = "voice.listening_started"
    LISTENING_STOPPED = "voice.listening_stopped"
    UTTERANCE_CAPTURED = "voice.utterance_captured"
    PARTIAL_TRANSCRIPT = "voice.partial_transcript"
    TRANSCRIBED = "voice.transcribed"
    RESPONSE_READY = "voice.response_ready"
    SPEAKING_STARTED = "voice.speaking_started"
    SPEAKING_FINISHED = "voice.speaking_finished"
    INTERRUPTED = "voice.interrupted"
    ERROR = "voice.error"

    # Added in Phase 7, published by SpeechQueue (core/speech/queue.py).
    QUEUED = "voice.queued"
    QUEUE_CLEARED = "voice.queue_cleared"
    QUEUE_SKIPPED = "voice.queue_skipped"

    # Added in Phase 8, published when a concrete VoicePipeline's
    # WakeWordPort fires while in WAITING_FOR_WAKE_WORD.
    WAKE_WORD_DETECTED = "voice.wake_word_detected"
