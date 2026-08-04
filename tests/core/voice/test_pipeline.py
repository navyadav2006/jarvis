from __future__ import annotations

import pytest

from jarvis.core.config.voice_config import VoiceConfig, WakeWordConfig
from jarvis.core.events import EventBus
from jarvis.core.voice.pipeline import VoicePipeline
from jarvis.core.voice.ports import (
    NullAudioPlayerPort,
    NullMicrophonePort,
    NullSpeechToTextPort,
    NullTextToSpeechPort,
    NullVoiceActivityDetector,
    NullWakeWordPort,
)
from jarvis.core.voice.types import VoiceEvents, VoiceState


def _echo_assistant(text: str, session_id: str) -> str:
    return text


def _build_kwargs(events: EventBus) -> dict:
    return dict(
        microphone=NullMicrophonePort(),
        wake_word=NullWakeWordPort(),
        vad=NullVoiceActivityDetector(),
        stt=NullSpeechToTextPort(),
        assistant=_echo_assistant,
        tts=NullTextToSpeechPort(),
        player=NullAudioPlayerPort(),
        config=VoiceConfig(),
        events=events,
    )


class MinimalVoicePipeline(VoicePipeline):
    """The smallest possible concrete subclass — proves VoicePipeline's
    abstract contract is actually implementable, the same role
    test_plugin_base.py's `Valid` class plays for PluginBase.
    """

    def start(self) -> None:
        self._set_state(VoiceState.LISTENING)
        self._publish(VoiceEvents.LISTENING_STARTED)

    def stop(self) -> None:
        self._set_state(VoiceState.IDLE)
        self._publish(VoiceEvents.LISTENING_STOPPED)

    def push_to_talk_press(self) -> None:
        self._set_state(VoiceState.LISTENING)

    def push_to_talk_release(self) -> None:
        self._set_state(VoiceState.THINKING)

    def interrupt(self) -> None:
        self._player.stop()
        self._set_state(VoiceState.LISTENING)
        self._publish(VoiceEvents.INTERRUPTED)


def test_cannot_instantiate_voice_pipeline_directly() -> None:
    with pytest.raises(TypeError):
        VoicePipeline(**_build_kwargs(EventBus()))  # type: ignore[abstract]


def test_concrete_subclass_starts_in_idle_state() -> None:
    pipeline = MinimalVoicePipeline(**_build_kwargs(EventBus()))
    assert pipeline.state == VoiceState.IDLE


def test_start_transitions_state_and_publishes_event() -> None:
    events = EventBus()
    received = []
    events.subscribe(VoiceEvents.LISTENING_STARTED, received.append)

    pipeline = MinimalVoicePipeline(**_build_kwargs(events))
    pipeline.start()

    assert pipeline.state == VoiceState.LISTENING
    assert len(received) == 1
    assert received[0].source == "voice_pipeline"


def test_stop_returns_to_idle_and_publishes_event() -> None:
    events = EventBus()
    received = []
    events.subscribe(VoiceEvents.LISTENING_STOPPED, received.append)

    pipeline = MinimalVoicePipeline(**_build_kwargs(events))
    pipeline.start()
    pipeline.stop()

    assert pipeline.state == VoiceState.IDLE
    assert len(received) == 1


def test_push_to_talk_press_and_release_transition_state() -> None:
    pipeline = MinimalVoicePipeline(**_build_kwargs(EventBus()))
    pipeline.push_to_talk_press()
    assert pipeline.state == VoiceState.LISTENING
    pipeline.push_to_talk_release()
    assert pipeline.state == VoiceState.THINKING


def test_interrupt_stops_player_and_returns_to_listening() -> None:
    events = EventBus()
    received = []
    events.subscribe(VoiceEvents.INTERRUPTED, received.append)
    pipeline = MinimalVoicePipeline(**_build_kwargs(events))

    pipeline.interrupt()

    assert pipeline.state == VoiceState.LISTENING
    assert len(received) == 1


def test_missing_abstract_method_prevents_instantiation() -> None:
    class Incomplete(VoicePipeline):
        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

        def push_to_talk_press(self) -> None:
            pass

        # push_to_talk_release and interrupt deliberately not implemented

    with pytest.raises(TypeError):
        Incomplete(**_build_kwargs(EventBus()))  # type: ignore[abstract]


class WakeWordGatedVoicePipeline(VoicePipeline):
    """A second concrete subclass, exercising Phase 8's wake-word-gating
    contract (start()'s and the class docstring's WAITING_FOR_WAKE_WORD
    behavior) without changing MinimalVoicePipeline's simpler one, which
    the tests above already depend on.
    """

    def start(self) -> None:
        if self._config.wake_word.enabled:
            self._set_state(VoiceState.WAITING_FOR_WAKE_WORD)
        else:
            self._set_state(VoiceState.LISTENING)
            self._publish(VoiceEvents.LISTENING_STARTED)

    def stop(self) -> None:
        self._set_state(VoiceState.IDLE)
        self._publish(VoiceEvents.LISTENING_STOPPED)

    def push_to_talk_press(self) -> None:
        self._set_state(VoiceState.LISTENING)

    def push_to_talk_release(self) -> None:
        self._set_state(VoiceState.THINKING)

    def interrupt(self) -> None:
        self._player.stop()
        self._set_state(VoiceState.LISTENING)
        self._publish(VoiceEvents.INTERRUPTED)

    def on_wake_word_detected(self, name: str) -> None:
        self._wake_word.reset()
        self._set_state(VoiceState.LISTENING)
        self._publish(VoiceEvents.WAKE_WORD_DETECTED, {"model": name})
        self._publish(VoiceEvents.LISTENING_STARTED)

    def end_conversation_turn(self) -> None:
        """Simulates "automatically resumes after conversations"."""
        if self._config.wake_word.enabled:
            self._wake_word.reset()
            self._set_state(VoiceState.WAITING_FOR_WAKE_WORD)
        else:
            self._set_state(VoiceState.IDLE)


def test_start_with_wake_word_enabled_waits_instead_of_listening() -> None:
    pipeline = WakeWordGatedVoicePipeline(**_build_kwargs(EventBus()))
    pipeline.start()
    assert pipeline.state == VoiceState.WAITING_FOR_WAKE_WORD


def test_start_with_wake_word_disabled_listens_immediately() -> None:
    kwargs = _build_kwargs(EventBus())
    kwargs["config"] = VoiceConfig(wake_word=WakeWordConfig(enabled=False))
    pipeline = WakeWordGatedVoicePipeline(**kwargs)
    pipeline.start()
    assert pipeline.state == VoiceState.LISTENING


def test_wake_word_detected_transitions_to_listening_and_publishes_event() -> None:
    events = EventBus()
    received = []
    events.subscribe(VoiceEvents.WAKE_WORD_DETECTED, received.append)
    pipeline = WakeWordGatedVoicePipeline(**_build_kwargs(events))
    pipeline.start()

    pipeline.on_wake_word_detected("hey_jarvis")

    assert pipeline.state == VoiceState.LISTENING
    assert len(received) == 1
    assert received[0].payload["model"] == "hey_jarvis"


def test_end_conversation_turn_resumes_waiting_for_wake_word() -> None:
    pipeline = WakeWordGatedVoicePipeline(**_build_kwargs(EventBus()))
    pipeline.start()
    pipeline.on_wake_word_detected("hey_jarvis")

    pipeline.end_conversation_turn()

    assert pipeline.state == VoiceState.WAITING_FOR_WAKE_WORD


def test_end_conversation_turn_without_wake_word_returns_to_idle() -> None:
    kwargs = _build_kwargs(EventBus())
    kwargs["config"] = VoiceConfig(wake_word=WakeWordConfig(enabled=False))
    pipeline = WakeWordGatedVoicePipeline(**kwargs)
    pipeline.start()

    pipeline.end_conversation_turn()

    assert pipeline.state == VoiceState.IDLE
