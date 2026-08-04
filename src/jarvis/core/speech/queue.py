"""SpeechQueue: the reusable engine for queueing and playing multiple
spoken responses, with runtime volume control and three distinct ways
to interrupt it.

A background worker thread drains a text queue: for each item, it
calls TextToSpeechPort.synthesize(), applies the current volume via
speech.audio.apply_gain(), and calls AudioPlayerPort.play() — then
polls `is_playing` until playback finishes before moving to the next
item. Polling (rather than requiring AudioPlayerPort to support a
completion callback) was chosen specifically so this works with *any*
AudioPlayerPort implementation, real or fake, without changing Phase
5's Protocol signature — see docs/architecture.md's Phase 7 section.

Like StreamingTranscriber, SpeechQueue's own logic has no required
third-party dependency: it depends only on TextToSpeechPort/
AudioPlayerPort (Protocols) and the standard library, which is what
lets its entire test suite run against fakes with neither piper-tts
nor any real audio output installed.

Three distinct ways to stop speech, deliberately not conflated into
one method:

  - `skip()`   — stop the current utterance, continue with the next
                 queued one (if any). "Not that one, but keep going."
  - `clear()`  — discard all pending queued text, but let whatever is
                 currently playing finish. "Don't say the rest."
  - `interrupt()` — stop the current utterance AND discard everything
                 pending. "Stop talking altogether" — what a future
                 VoicePipeline.interrupt() (barge-in) would call.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from typing import Any

from jarvis.core.config.voice_config import SpeechQueueConfig
from jarvis.core.events import EventBus
from jarvis.core.exceptions import SpeechQueueFullError
from jarvis.core.speech.audio import apply_gain
from jarvis.core.voice.ports import AudioPlayerPort, TextToSpeechPort
from jarvis.core.voice.types import VoiceEvents

logger = logging.getLogger(__name__)


class SpeechQueue:
    def __init__(
        self,
        *,
        tts: TextToSpeechPort,
        player: AudioPlayerPort,
        config: SpeechQueueConfig,
        initial_volume: float = 1.0,
        events: EventBus | None = None,
    ) -> None:
        self._tts = tts
        self._player = player
        self._config = config
        self._events = events

        self._lock = threading.Lock()
        self._pending: deque[str] = deque()
        self._volume = initial_volume

        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._worker: threading.Thread | None = None

    # -- lifecycle -------------------------------------------------------

    def start(self) -> None:
        """Start the background worker. Idempotent if already started."""
        if self._worker is not None:
            return
        self._stop_event.clear()
        self._worker = threading.Thread(
            target=self._run, name="speech-queue", daemon=True
        )
        self._worker.start()

    def close(self) -> None:
        """Stop the worker thread and any in-progress playback. Safe to
        call whether or not start() was ever called.
        """
        self._stop_event.set()
        self._wake_event.set()
        self._player.stop()
        if self._worker is not None:
            self._worker.join(timeout=5)
            self._worker = None

    # -- queue control -----------------------------------------------------

    def enqueue(self, text: str) -> None:
        """Add `text` to the queue. Raises SpeechQueueFullError if
        `config.max_queue_size` pending items are already queued.
        """
        with self._lock:
            if self._config.max_queue_size is not None and len(self._pending) >= (
                self._config.max_queue_size
            ):
                raise SpeechQueueFullError(
                    f"speech queue is full ({self._config.max_queue_size} pending items)"
                )
            self._pending.append(text)
        self._publish(VoiceEvents.QUEUED, {"text": text, "pending": self.pending_count})
        self._wake_event.set()

    def skip(self) -> None:
        """Stop the current utterance; the worker continues with the next
        queued item, if any. A no-op if nothing is currently playing.
        """
        self._player.stop()
        self._publish(VoiceEvents.QUEUE_SKIPPED, {})

    def clear(self) -> None:
        """Discard all pending queued text. Whatever is currently playing
        is left to finish.
        """
        with self._lock:
            dropped = len(self._pending)
            self._pending.clear()
        self._publish(VoiceEvents.QUEUE_CLEARED, {"dropped": dropped})

    def interrupt(self) -> None:
        """Stop the current utterance AND discard everything pending —
        what a future VoicePipeline.interrupt() (barge-in) calls.
        """
        with self._lock:
            dropped = len(self._pending)
            self._pending.clear()
        self._player.stop()
        self._publish(VoiceEvents.INTERRUPTED, {"dropped": dropped})

    def set_volume(self, volume: float) -> None:
        """Change the gain applied to future playback (including items
        already queued but not yet spoken). Does not affect audio
        already handed to the player for the current utterance.
        """
        if volume < 0:
            raise ValueError(f"volume must be >= 0, got {volume}")
        with self._lock:
            self._volume = volume

    @property
    def volume(self) -> float:
        with self._lock:
            return self._volume

    @property
    def is_speaking(self) -> bool:
        return self._player.is_playing

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)

    # -- worker thread -----------------------------------------------------

    def _run(self) -> None:
        while not self._stop_event.is_set():
            text = self._next_text()
            if text is None:
                self._wake_event.wait(timeout=self._config.poll_interval_seconds)
                self._wake_event.clear()
                continue
            self._speak(text)

    def _next_text(self) -> str | None:
        with self._lock:
            return self._pending.popleft() if self._pending else None

    def _speak(self, text: str) -> None:
        try:
            audio = self._tts.synthesize(text)
        except Exception:
            logger.exception("Speech synthesis failed for text=%r", text)
            self._publish(VoiceEvents.ERROR, {"reason": "synthesis_failed", "text": text})
            return

        audio = apply_gain(audio, self.volume)

        self._publish(VoiceEvents.SPEAKING_STARTED, {"text": text})
        self._player.play(audio)
        while self._player.is_playing and not self._stop_event.is_set():
            self._stop_event.wait(timeout=self._config.poll_interval_seconds)
        self._publish(VoiceEvents.SPEAKING_FINISHED, {"text": text})

    def _publish(self, name: str, payload: dict[str, Any]) -> None:
        if self._events is not None:
            self._events.publish(name, payload, source="speech_queue")
