"""VoicePipeline: the contract for coordinating Microphone -> Speech-to-
Text -> Assistant -> Text-to-Speech across five supported interaction
styles — continuous listening, push-to-talk, conversation mode,
background listening, and voice interruption (barge-in).

This is an interface only: an ABC with abstract lifecycle methods,
matching this phase's scope ("design the interfaces only"). No
concrete subclass exists yet that actually threads audio between real
ports, and nothing in main.py or the orchestrator constructs or
registers one. A concrete implementation — e.g. running the
listen/transcribe/respond/speak loop on a background thread, wired to
real Whisper.cpp/Piper/microphone backends — is future work. See
docs/architecture.md's Phase 5 section for exactly what's deferred and
why.

Why an ABC and not a Protocol, unlike every port in ports.py:
VoicePipeline is a stateful lifecycle object (like PluginBase from
Phase 1), not a stateless wrapper around one external resource (like
MicrophonePort). The concrete constructor validates and stores its
dependencies; state tracking (`state` property, `_set_state()`) and
event publishing (`_publish()`) are shared behavior every real
implementation needs — the same shape PluginBase uses for `name`
validation and `on_unload`'s default no-op.

Four of the five required behaviors are config-driven modifiers of
`start()`'s behavior, not separate abstract methods:

  - Continuous vs. push-to-talk is `config.listening.mode` — `start()`
    either begins capturing immediately (using the VoiceActivityDetector
    to segment utterances) or arms the pipeline for
    push_to_talk_press()/release().
  - Background listening is `config.listening.background` — whether a
    concrete implementation runs its listen loop on a separate
    thread/task rather than blocking the caller of `start()`.
  - Conversation mode is `config.listening.conversation_mode` (+
    `conversation_timeout_seconds`) — after speaking a response, a
    concrete implementation either returns to IDLE (or, since Phase 8,
    WAITING_FOR_WAKE_WORD — see below) or automatically re-enters
    LISTENING for the next turn.

Voice interruption is the one behavior with its own abstract method
(`interrupt()`), because unlike the other three it isn't a variant of
how `start()` behaves — it's an action that can happen *during*
SPEAKING, from an entirely different call path (e.g. the
VoiceActivityDetector firing mid-playback on a background thread).

Wake word gating (Phase 8) is a sixth config-driven modifier,
`config.wake_word.enabled`, orthogonal to which of the five styles
above is active but only meaningful in CONTINUOUS mode — PUSH_TO_TALK's
button is already an explicit activation, so implementations are not
required to consult `wake_word` there. When enabled, `start()` (and,
per "automatically resumes after conversations" below, the return to
idle after a conversation turn) transitions to WAITING_FOR_WAKE_WORD
instead of LISTENING/IDLE, feeding captured audio to
`wake_word.process()` — a cheap, purpose-built classifier — instead of
`vad`/`stt`, until a wake word fires. This is what keeps "runs
continuously" and "consumes minimal CPU" compatible: the expensive
stages (VAD segmentation, whisper.cpp inference) never run while idle.

"Automatically resumes after conversations": whenever a concrete
implementation would otherwise return to IDLE after finishing a turn —
a single non-conversation-mode exchange finishing, or
conversation_mode's `conversation_timeout_seconds` elapsing with no
further utterance — it must instead return to WAITING_FOR_WAKE_WORD if
`config.wake_word.enabled`, calling `wake_word.reset()` first. This is
what "resumes" means: no manual restart is needed to speak to the
assistant again, but the CPU cost of doing so stays at "one cheap
wake-word model," not "an open microphone running VAD and STT."
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from jarvis.core.config.voice_config import VoiceConfig
from jarvis.core.events import EventBus
from jarvis.core.voice.ports import (
    AssistantHandler,
    AudioPlayerPort,
    MicrophonePort,
    SpeechToTextPort,
    TextToSpeechPort,
    VoiceActivityDetector,
    WakeWordPort,
)
from jarvis.core.voice.types import VoiceState

logger = logging.getLogger(__name__)


class VoicePipeline(ABC):
    def __init__(
        self,
        *,
        microphone: MicrophonePort,
        wake_word: WakeWordPort,
        vad: VoiceActivityDetector,
        stt: SpeechToTextPort,
        assistant: AssistantHandler,
        tts: TextToSpeechPort,
        player: AudioPlayerPort,
        config: VoiceConfig,
        events: EventBus,
    ) -> None:
        self._microphone = microphone
        self._wake_word = wake_word
        self._vad = vad
        self._stt = stt
        self._assistant = assistant
        self._tts = tts
        self._player = player
        self._config = config
        self._events = events
        self._state = VoiceState.IDLE

    @property
    def state(self) -> VoiceState:
        return self._state

    @abstractmethod
    def start(self) -> None:
        """Begin listening per `config.listening.mode`:

        - CONTINUOUS: if `config.wake_word.enabled`, transition to
          WAITING_FOR_WAKE_WORD and feed captured audio to
          `wake_word.process()` instead of `vad`/`stt`. Once it returns
          a name, publish VoiceEvents.WAKE_WORD_DETECTED, call
          `wake_word.reset()`, and move into LISTENING — using `vad` to
          segment utterances, transcribing and responding automatically
          from there. If wake word is disabled, skip straight to
          LISTENING and start segmenting immediately.
        - PUSH_TO_TALK: arm the pipeline; capture only happens between
          push_to_talk_press()/push_to_talk_release() calls. `wake_word`
          is not consulted in this mode — pressing the button is
          already an explicit activation.

        Must publish VoiceEvents.LISTENING_STARTED once LISTENING is
        actually entered (not merely WAITING_FOR_WAKE_WORD). If
        `config.listening.background` is True, must not block the
        caller — the listen loop runs on its own thread/task.
        """
        raise NotImplementedError

    @abstractmethod
    def stop(self) -> None:
        """Stop listening and/or speaking entirely and return to IDLE.
        Must publish VoiceEvents.LISTENING_STOPPED. Safe to call from
        any state.
        """
        raise NotImplementedError

    @abstractmethod
    def push_to_talk_press(self) -> None:
        """Begin capturing an utterance. Only meaningful when
        `config.listening.mode` is PUSH_TO_TALK; implementations should
        raise if called while in CONTINUOUS mode.
        """
        raise NotImplementedError

    @abstractmethod
    def push_to_talk_release(self) -> None:
        """End the held utterance and run it through `stt`, `assistant`,
        `tts`, and `player`. Only meaningful in PUSH_TO_TALK mode.
        """
        raise NotImplementedError

    @abstractmethod
    def interrupt(self) -> None:
        """Stop in-progress TTS playback immediately (barge-in) and
        return to LISTENING, if `config.listening.allow_interruption`
        is True. Must publish VoiceEvents.INTERRUPTED. A no-op (not an
        error) if nothing is currently playing, and a no-op if
        interruption is disabled by config.
        """
        raise NotImplementedError

    def _set_state(self, state: VoiceState) -> None:
        logger.debug("Voice pipeline state: %s -> %s", self._state.value, state.value)
        self._state = state

    def _publish(self, name: str, payload: dict[str, Any] | None = None) -> None:
        self._events.publish(name, payload or {}, source="voice_pipeline")
