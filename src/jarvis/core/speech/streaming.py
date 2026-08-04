"""StreamingTranscriber: the reusable real-time speech engine.

Buffers AudioChunks fed to it via `feed()`, uses a VoiceActivityDetector
to detect a speaker pausing (finalizing an utterance) and emits low-
latency partial transcriptions while speech is ongoing. Deliberately
decoupled from MicrophonePort — it consumes whatever AudioChunks it's
given, from a real microphone, a WAV file, or a test double — which is
what makes it "reusable" rather than tied to one audio source or one
pipeline.

Every duration this class reasons about — pause detection, max
utterance length, the no-speech timeout, and partial-result cadence —
is computed from the *audio data's own* duration (via
speech.audio.chunk_duration_seconds), not wall-clock time elapsed
between feed() calls. This is deliberate:

  - It makes the whole state machine a pure function of the chunks
    it's given, fully deterministic and testable with synthetic audio
    — no time mocking required, and tests run in milliseconds instead
    of waiting out real timeouts.
  - It's *more correct*, not just more convenient: "how long has the
    speaker been silent" should mean silence in the recording, not
    however long Python happened to take between two feed() calls
    (which could be skewed by GC pauses, scheduling, or a slow VAD
    call).

The one exception is `inference_timeout_seconds`, which bounds the
whisper.cpp call itself — that genuinely is wall-clock time, since
inference duration has no relationship to the audio's length. Python
cannot forcibly interrupt a blocking native call, so it's enforced by
running the call in a worker thread and abandoning (not killing) it if
it doesn't finish in time; see `_transcribe_with_timeout`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError

from jarvis.core.config.voice_config import StreamingConfig
from jarvis.core.events import EventBus
from jarvis.core.exceptions import NoSpeechTimeoutError, TranscriptionTimeoutError
from jarvis.core.speech.audio import chunk_duration_seconds, concat_chunks
from jarvis.core.voice.ports import SpeechToTextPort, VoiceActivityDetector
from jarvis.core.voice.types import AudioChunk, TranscriptionResult, VoiceEvents

logger = logging.getLogger(__name__)


class StreamingTranscriber:
    def __init__(
        self,
        *,
        stt: SpeechToTextPort,
        vad: VoiceActivityDetector,
        config: StreamingConfig,
        events: EventBus | None = None,
        on_partial: Callable[[TranscriptionResult], None] | None = None,
    ) -> None:
        self._stt = stt
        self._vad = vad
        self._config = config
        self._events = events
        self._on_partial = on_partial
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="whisper-inference")
        self._reset()

    def start(self) -> None:
        """Reset buffering state. feed() also auto-starts on first call,
        so this only needs to be called explicitly to reset mid-stream
        (e.g. after a caller-driven cancellation).
        """
        self._reset()

    def feed(self, chunk: AudioChunk) -> TranscriptionResult | None:
        """Feed one chunk of audio. Returns a final TranscriptionResult
        when an utterance completes (a detected pause, or the max-
        utterance timeout), otherwise None. Partial (is_final=False)
        results are never returned from feed() — only delivered via
        `on_partial`/the EventBus — which keeps this method's contract
        simple: either "nothing yet" or "here is the finished utterance."

        Raises NoSpeechTimeoutError if no_speech_timeout_seconds of
        audio passes without any speech being detected.
        """
        duration = chunk_duration_seconds(chunk)
        is_speech = self._vad.is_speech(chunk)

        if is_speech:
            self._speech_started = True
            self._silence_seconds = 0.0
            self._no_speech_seconds = 0.0
            self._buffer.append(chunk)
            self._buffered_speech_seconds += duration
            self._since_last_partial_seconds += duration
        elif self._speech_started:
            # Keep buffering trailing silence too, for a natural-sounding
            # cutoff rather than clipping the utterance mid-word.
            self._silence_seconds += duration
            self._buffer.append(chunk)
        else:
            self._no_speech_seconds += duration
            if self._no_speech_seconds >= self._config.no_speech_timeout_seconds:
                self._publish(VoiceEvents.ERROR, {"reason": "no_speech_timeout"})
                raise NoSpeechTimeoutError(
                    f"No speech detected within {self._config.no_speech_timeout_seconds}s"
                )
            return None

        if self._silence_seconds >= self._config.pause_duration_seconds:
            return self._finalize()

        if self._buffered_speech_seconds >= self._config.max_utterance_seconds:
            logger.warning("Max utterance duration reached; forcing finalize")
            return self._finalize()

        if self._since_last_partial_seconds >= self._config.partial_interval_seconds:
            self._emit_partial()

        return None

    def force_finalize(self) -> TranscriptionResult | None:
        """Finalize whatever's currently buffered immediately, ignoring
        `pause_duration_seconds` — used by push-to-talk, where button
        release is the end-of-utterance signal instead of a detected
        pause. Returns None if nothing has been buffered yet.
        """
        if not self._buffer:
            return None
        return self._finalize()

    def close(self) -> None:
        """Release the inference worker thread. Any in-flight call is
        abandoned, not cancelled (Python cannot interrupt a running
        native call) — it will finish in the background and its result
        is simply discarded.
        """
        self._executor.shutdown(wait=False, cancel_futures=True)

    # -- internals -------------------------------------------------------

    def _reset(self) -> None:
        self._buffer: list[AudioChunk] = []
        self._speech_started = False
        self._silence_seconds = 0.0
        self._no_speech_seconds = 0.0
        self._buffered_speech_seconds = 0.0
        self._since_last_partial_seconds = 0.0

    def _emit_partial(self) -> None:
        self._since_last_partial_seconds = 0.0
        audio = concat_chunks(self._buffer)
        try:
            result = self._transcribe_with_timeout(audio, is_final=False)
        except TranscriptionTimeoutError:
            logger.warning("Partial transcription timed out; skipping this partial")
            return
        self._publish(VoiceEvents.PARTIAL_TRANSCRIPT, {"text": result.text})
        if self._on_partial is not None:
            self._on_partial(result)

    def _finalize(self) -> TranscriptionResult:
        if not self._buffer:
            self._reset()
            return TranscriptionResult(text="", is_final=True)

        audio = concat_chunks(self._buffer)
        result = self._transcribe_with_timeout(audio, is_final=True)
        self._publish(
            VoiceEvents.TRANSCRIBED, {"text": result.text, "language": result.language}
        )
        self._reset()
        return result

    def _transcribe_with_timeout(self, audio: AudioChunk, *, is_final: bool) -> TranscriptionResult:
        future = self._executor.submit(self._stt.transcribe, audio)
        try:
            result = future.result(timeout=self._config.inference_timeout_seconds)
        except FutureTimeoutError as exc:
            self._publish(VoiceEvents.ERROR, {"reason": "inference_timeout"})
            raise TranscriptionTimeoutError(
                f"whisper.cpp did not return within {self._config.inference_timeout_seconds}s"
            ) from exc
        return TranscriptionResult(
            text=result.text,
            confidence=result.confidence,
            is_final=is_final,
            language=result.language,
        )

    def _publish(self, name: str, payload: dict | None = None) -> None:
        if self._events is not None:
            self._events.publish(name, payload or {}, source="streaming_transcriber")
