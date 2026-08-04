from __future__ import annotations

import time

import pytest

from jarvis.core.config.voice_config import (
    ListeningConfig,
    ListeningMode,
    SpeechQueueConfig,
    StreamingConfig,
    VoiceConfig,
    WakeWordConfig,
)
from jarvis.core.events import EventBus
from jarvis.core.speech.jarvis_pipeline import JarvisVoicePipeline
from jarvis.core.voice.types import VoiceState

from .conftest import (
    FakeAssistant,
    FakeAudioPlayerPort,
    FakeSTT,
    FakeTTS,
    QueueMicrophonePort,
    ScriptedWakeWord,
    ToggleVAD,
    make_chunk,
)


def wait_until(condition, *, timeout: float = 2.0, interval: float = 0.01) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(interval)
    raise AssertionError(f"condition not met within {timeout}s")


def _speak_chunk(mic, vad, *, speech: bool) -> None:
    """Push one chunk with `vad.speech` set for it, and block until the
    audio-loop thread has actually consumed it (called is_speech()) —
    ToggleVAD's value is read at call-time, not push-time, so without
    this a test flipping `vad.speech` twice in quick succession can
    race the consumer thread and have both pushed chunks see the same
    (wrong) value.
    """
    before = vad.calls
    vad.speech = speech
    mic.push(make_chunk(0.05))
    wait_until(lambda: vad.calls > before)


def _config(
    *, mode=ListeningMode.CONTINUOUS, wake_word=True, conversation_mode=False,
    conversation_timeout=0.2, allow_interruption=True,
) -> VoiceConfig:
    return VoiceConfig(
        wake_word=WakeWordConfig(enabled=wake_word),
        listening=ListeningConfig(
            mode=mode,
            conversation_mode=conversation_mode,
            conversation_timeout_seconds=conversation_timeout,
            allow_interruption=allow_interruption,
        ),
        streaming=StreamingConfig(
            pause_duration_seconds=0.05,
            max_utterance_seconds=5.0,
            no_speech_timeout_seconds=5.0,
            partial_interval_seconds=5.0,
            inference_timeout_seconds=2.0,
        ),
        queue=SpeechQueueConfig(poll_interval_seconds=0.01),
    )


def _build(config: VoiceConfig, *, player=None, tts=None):
    mic = QueueMicrophonePort()
    wake_word = ScriptedWakeWord(trigger_after=1)
    vad = ToggleVAD()
    stt = FakeSTT(text="turn on the lights")
    assistant = FakeAssistant(response="done")
    events = EventBus()
    pipeline = JarvisVoicePipeline(
        microphone=mic,
        wake_word=wake_word,
        vad=vad,
        stt=stt,
        assistant=assistant,
        tts=tts or FakeTTS(audio_seconds=0.02),
        player=player or FakeAudioPlayerPort(play_seconds=0.2),
        config=config,
        events=events,
        session_id="voice-test",
    )
    return pipeline, mic, wake_word, vad, assistant


def test_wake_word_then_utterance_produces_a_spoken_response() -> None:
    pipeline, mic, wake_word, vad, assistant = _build(_config())
    pipeline.start()

    mic.push(make_chunk(0.05))  # triggers the wake word
    wait_until(lambda: pipeline.state == VoiceState.LISTENING)

    _speak_chunk(mic, vad, speech=True)
    _speak_chunk(mic, vad, speech=False)

    wait_until(lambda: assistant.calls == [("turn on the lights", "voice-test")])
    wait_until(lambda: pipeline.state == VoiceState.WAITING_FOR_WAKE_WORD)
    pipeline.stop()


def test_no_wake_word_match_never_starts_listening() -> None:
    pipeline, mic, wake_word, vad, assistant = _build(_config())
    wake_word.trigger_after = 1000  # never fires within this test
    pipeline.start()

    mic.push(make_chunk(0.05))
    mic.push(make_chunk(0.05))
    time.sleep(0.1)

    assert pipeline.state == VoiceState.WAITING_FOR_WAKE_WORD
    assert assistant.calls == []
    pipeline.stop()


def test_barge_in_interrupts_playback_and_returns_to_listening() -> None:
    player = FakeAudioPlayerPort(play_seconds=5.0)  # long enough to interrupt mid-playback
    pipeline, mic, wake_word, vad, assistant = _build(_config(), player=player)
    pipeline.start()

    mic.push(make_chunk(0.05))
    wait_until(lambda: pipeline.state == VoiceState.LISTENING)
    _speak_chunk(mic, vad, speech=True)
    _speak_chunk(mic, vad, speech=False)
    wait_until(lambda: pipeline.state == VoiceState.SPEAKING)

    _speak_chunk(mic, vad, speech=True)

    wait_until(lambda: player.stop_calls >= 1)
    wait_until(lambda: pipeline.state == VoiceState.LISTENING)
    pipeline.stop()


def test_interrupt_is_noop_when_not_speaking() -> None:
    pipeline, *_ = _build(_config())
    pipeline.start()
    pipeline.interrupt()  # must not raise
    assert pipeline.state == VoiceState.WAITING_FOR_WAKE_WORD
    pipeline.stop()


def test_conversation_mode_captures_a_follow_up_without_a_new_wake_word() -> None:
    pipeline, mic, wake_word, vad, assistant = _build(_config(conversation_mode=True))
    pipeline.start()

    mic.push(make_chunk(0.05))
    wait_until(lambda: pipeline.state == VoiceState.LISTENING)
    _speak_chunk(mic, vad, speech=True)
    _speak_chunk(mic, vad, speech=False)
    wait_until(lambda: len(assistant.calls) == 1)

    wait_until(lambda: pipeline.state == VoiceState.LISTENING)  # back to listening, no wake word
    _speak_chunk(mic, vad, speech=True)
    _speak_chunk(mic, vad, speech=False)
    wait_until(lambda: len(assistant.calls) == 2)

    assert wake_word.calls == 1  # only the very first turn needed a wake word
    pipeline.stop()


def test_conversation_timeout_resumes_waiting_for_wake_word() -> None:
    pipeline, mic, wake_word, vad, assistant = _build(
        _config(conversation_mode=True, conversation_timeout=0.1)
    )
    pipeline.start()

    mic.push(make_chunk(0.05))
    wait_until(lambda: pipeline.state == VoiceState.LISTENING)
    _speak_chunk(mic, vad, speech=True)
    _speak_chunk(mic, vad, speech=False)
    wait_until(lambda: len(assistant.calls) == 1)

    wait_until(lambda: pipeline.state == VoiceState.WAITING_FOR_WAKE_WORD, timeout=1.0)
    pipeline.stop()


def test_push_to_talk_flow() -> None:
    pipeline, mic, wake_word, vad, assistant = _build(
        _config(mode=ListeningMode.PUSH_TO_TALK, wake_word=False)
    )
    pipeline.start()
    assert pipeline.state == VoiceState.IDLE

    pipeline.push_to_talk_press()
    wait_until(lambda: pipeline.state == VoiceState.LISTENING)
    _speak_chunk(mic, vad, speech=True)
    pipeline.push_to_talk_release()

    wait_until(lambda: assistant.calls == [("turn on the lights", "voice-test")])
    wait_until(lambda: pipeline.state == VoiceState.IDLE)
    pipeline.stop()


def test_push_to_talk_press_in_continuous_mode_raises() -> None:
    pipeline, *_ = _build(_config(mode=ListeningMode.CONTINUOUS))
    with pytest.raises(ValueError):
        pipeline.push_to_talk_press()


def test_stop_shuts_down_cleanly() -> None:
    pipeline, mic, *_ = _build(_config())
    pipeline.start()
    wait_until(lambda: pipeline.state == VoiceState.WAITING_FOR_WAKE_WORD)
    pipeline.stop()
    assert pipeline.state == VoiceState.IDLE
    assert mic.is_active is False


def test_response_ready_event_carries_latency() -> None:
    pipeline, mic, wake_word, vad, assistant = _build(_config())
    events_seen = []
    pipeline._events.subscribe(
        "voice.response_ready", lambda e: events_seen.append(e.payload)
    )
    pipeline.start()

    mic.push(make_chunk(0.05))
    wait_until(lambda: pipeline.state == VoiceState.LISTENING)
    _speak_chunk(mic, vad, speech=True)
    _speak_chunk(mic, vad, speech=False)

    wait_until(lambda: len(events_seen) == 1)
    assert events_seen[0]["latency_seconds"] >= 0
    pipeline.stop()
