"""JarvisVoicePipeline: the first concrete VoicePipeline (Phase 11) —
wires every port/backend built in Phases 5-10 into one running loop:

    WakeWordPort -> StreamingTranscriber(VAD+SpeechToTextPort) ->
    AssistantHandler (-> Orchestrator: IntentRecognizer -> capability
    or Cowork) -> SpeechQueue(TextToSpeechPort+AudioPlayerPort)

This class builds StreamingTranscriber/SpeechQueue itself from the raw
ports VoicePipeline.__init__ already stores — the ABC's constructor
signature (Phase 5) is unchanged, so this lives in core/speech/, not
core/voice/, matching the existing one-way dependency rule
(core/speech/ depends on core/voice/, never the reverse).

A single background thread (`_audio_loop`) reads the microphone
continuously and branches on the pipeline's current VoiceState — the
same "always running, cheap when idle" shape Phase 8's wake-word gating
already established, just now with somewhere for LISTENING/SPEAKING to
go. `AssistantHandler` is expected to be
``lambda text, sid: orchestrator.handle(Request(text=text,
session_id=sid, source="voice")).text or ""`` (Phase 5's documented
shape) — which is also how this pipeline reaches Cowork: Orchestrator
already decides local-vs-Cowork and executes any returned plan, so
nothing here needs to know Cowork exists at all.

Latency: `voice.response_ready` events include `latency_seconds`
(utterance-finalized -> response text ready) and
`voice.speaking_started` events include `total_latency_seconds`
(utterance-finalized -> first audio played) — see
scripts/benchmark_voice_latency.py, which exercises this class with
fast fakes to produce docs/benchmarks/voice_latency.md.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from jarvis.core.config.voice_config import ListeningMode
from jarvis.core.exceptions import NoSpeechTimeoutError
from jarvis.core.speech.queue import SpeechQueue
from jarvis.core.speech.streaming import StreamingTranscriber
from jarvis.core.voice.pipeline import VoicePipeline
from jarvis.core.voice.types import TranscriptionResult, VoiceEvents, VoiceState

logger = logging.getLogger(__name__)

_MIC_READ_TIMEOUT_SECONDS = 0.05  # bounds barge-in/speaking-finished detection latency


class JarvisVoicePipeline(VoicePipeline):
    def __init__(self, *, session_id: str = "voice", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        # VoicePipeline.__init__ (Phase 5) doesn't carry a session_id —
        # it's a voice-specific concept, not part of the shared ABC
        # contract. One pipeline instance is one ongoing voice
        # conversation, so a single id for its lifetime is enough.
        self._session_id = session_id
        self._transcriber = StreamingTranscriber(
            stt=self._stt, vad=self._vad, config=self._config.streaming, events=self._events
        )
        self._speech_queue = SpeechQueue(
            tts=self._tts,
            player=self._player,
            config=self._config.queue,
            initial_volume=self._config.tts.volume,
            events=self._events,
        )
        self._worker: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._conversation_timer: threading.Timer | None = None
        self._speech_observed_playing = False

    # -- VoicePipeline contract -------------------------------------------

    def start(self) -> None:
        if self._worker is not None:
            return
        self._stop_event.clear()
        self._microphone.start()
        self._speech_queue.start()

        mode = self._config.listening.mode
        if mode == ListeningMode.CONTINUOUS and self._config.wake_word.enabled:
            self._wake_word.reset()
            self._set_state(VoiceState.WAITING_FOR_WAKE_WORD)
        elif mode == ListeningMode.CONTINUOUS:
            self._enter_listening()
        else:
            self._set_state(VoiceState.IDLE)  # push-to-talk: armed, not capturing

        self._worker = threading.Thread(
            target=self._audio_loop, name="jarvis-voice-pipeline", daemon=True
        )
        self._worker.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._cancel_conversation_timer()
        self._microphone.stop()
        self._speech_queue.close()
        self._transcriber.close()
        if self._worker is not None:
            self._worker.join(timeout=5)
            self._worker = None
        self._set_state(VoiceState.IDLE)
        self._publish(VoiceEvents.LISTENING_STOPPED)

    def push_to_talk_press(self) -> None:
        if self._config.listening.mode != ListeningMode.PUSH_TO_TALK:
            raise ValueError("push_to_talk_press() requires listening.mode == push_to_talk")
        self._enter_listening()

    def push_to_talk_release(self) -> None:
        if self._config.listening.mode != ListeningMode.PUSH_TO_TALK:
            raise ValueError("push_to_talk_release() requires listening.mode == push_to_talk")
        self._set_state(VoiceState.TRANSCRIBING)
        result = self._transcriber.force_finalize()
        if result is not None:
            self._on_utterance(result)
        else:
            self._resume_waiting()

    def interrupt(self) -> None:
        if not self._config.listening.allow_interruption:
            return
        if not self._speech_queue.is_speaking:
            return
        self._do_interrupt()

    # -- the always-on audio loop ------------------------------------------

    def _audio_loop(self) -> None:
        # SPEAKING is checked whether or not a chunk arrived this
        # iteration (unlike the other branches) because playback
        # finishing has nothing to do with new audio arriving — this is
        # what lets one thread both watch for barge-in *and* notice
        # playback completion without ever blocking on either.
        while not self._stop_event.is_set():
            chunk = self._microphone.read(timeout=_MIC_READ_TIMEOUT_SECONDS)
            state = self._state
            if state == VoiceState.SPEAKING:
                self._tick_speaking(chunk)
                if chunk is None:
                    # A MicrophonePort is allowed to return None
                    # instantly rather than actually blocking for
                    # `timeout` (NullMicrophonePort does) — without this,
                    # such a port would turn this branch into a
                    # busy-spin that starves other threads of the GIL.
                    self._stop_event.wait(timeout=0.005)
                continue
            if chunk is None:
                self._stop_event.wait(timeout=0.005)  # same busy-spin guard as above
                continue
            if state == VoiceState.WAITING_FOR_WAKE_WORD:
                name = self._wake_word.process(chunk)
                if name is not None:
                    self._wake_word.reset()
                    self._publish(VoiceEvents.WAKE_WORD_DETECTED, {"model": name})
                    self._enter_listening()
            elif state == VoiceState.LISTENING:
                self._feed_transcriber(chunk)
            # TRANSCRIBING/THINKING/IDLE/INTERRUPTED: no audio is consumed.

    def _tick_speaking(self, chunk: Any) -> None:
        if chunk is not None and self._config.listening.allow_interruption:
            if self._vad.is_speech(chunk):
                self._do_interrupt()
                return
        if self._speech_queue.is_speaking:
            self._speech_observed_playing = True
        elif self._speech_observed_playing and self._speech_queue.pending_count == 0:
            self._finish_speaking()

    def _feed_transcriber(self, chunk: Any) -> None:
        try:
            result = self._transcriber.feed(chunk)
        except NoSpeechTimeoutError:
            self._transcriber.start()
            if self._config.listening.conversation_mode:
                self._resume_waiting()
            return
        if result is not None:
            self._set_state(VoiceState.TRANSCRIBING)
            self._on_utterance(result)

    # -- one full turn -------------------------------------------------------

    def _on_utterance(self, result: TranscriptionResult) -> None:
        self._cancel_conversation_timer()
        if not result.text.strip():
            self._resume_waiting()
            return

        utterance_done = time.monotonic()
        self._publish(
            VoiceEvents.TRANSCRIBED, {"text": result.text, "language": result.language}
        )
        self._set_state(VoiceState.THINKING)

        response_text = self._assistant(result.text, self._session_id) or ""
        response_ready = time.monotonic()
        self._publish(
            VoiceEvents.RESPONSE_READY,
            {
                "text": response_text,
                # STT-finalize -> response text ready (excludes TTS/queueing
                # — see SpeechQueue's own voice.speaking_started event for
                # when audio actually starts playing).
                "latency_seconds": response_ready - utterance_done,
            },
        )

        self._speech_observed_playing = False
        self._set_state(VoiceState.SPEAKING)
        self._speech_queue.enqueue(response_text)
        # Completion (and barge-in) is now the audio loop's job — see
        # _tick_speaking() — so this method returns immediately,
        # letting the same thread keep reading mic chunks while
        # playback runs instead of blocking here. SPEAKING_STARTED/
        # SPEAKING_FINISHED are NOT re-published here: SpeechQueue
        # (Phase 7) already owns those two event names on this same
        # EventBus, with its own payload shape — publishing them again
        # here with a different shape would make subscribers guess
        # which payload they got.

    def _finish_speaking(self) -> None:
        if self._config.listening.conversation_mode:
            self._enter_listening()
            self._arm_conversation_timeout()
        else:
            self._resume_waiting()

    # -- state transitions -----------------------------------------------

    def _enter_listening(self) -> None:
        self._transcriber.start()
        self._set_state(VoiceState.LISTENING)
        self._publish(VoiceEvents.LISTENING_STARTED)

    def _resume_waiting(self) -> None:
        self._cancel_conversation_timer()
        wake_word_active = (
            self._config.wake_word.enabled
            and self._config.listening.mode == ListeningMode.CONTINUOUS
        )
        if wake_word_active:
            self._wake_word.reset()
            self._set_state(VoiceState.WAITING_FOR_WAKE_WORD)
        else:
            self._set_state(VoiceState.IDLE)

    def _do_interrupt(self) -> None:
        self._speech_queue.interrupt()
        self._cancel_conversation_timer()
        self._set_state(VoiceState.INTERRUPTED)
        self._publish(VoiceEvents.INTERRUPTED, {})
        self._enter_listening()

    def _arm_conversation_timeout(self) -> None:
        self._cancel_conversation_timer()
        timeout = self._config.listening.conversation_timeout_seconds
        self._conversation_timer = threading.Timer(timeout, self._on_conversation_timeout)
        self._conversation_timer.daemon = True
        self._conversation_timer.start()

    def _on_conversation_timeout(self) -> None:
        if self._state == VoiceState.LISTENING:
            self._resume_waiting()

    def _cancel_conversation_timer(self) -> None:
        if self._conversation_timer is not None:
            self._conversation_timer.cancel()
            self._conversation_timer = None
