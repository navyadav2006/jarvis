from __future__ import annotations

from jarvis.core.config.voice_config import StreamingConfig
from jarvis.core.events import EventBus
from jarvis.core.exceptions import NoSpeechTimeoutError, TranscriptionTimeoutError
from jarvis.core.speech.streaming import StreamingTranscriber
from jarvis.core.voice.types import VoiceEvents

from .conftest import FakeSTT, ScriptedVAD, make_chunk


def test_pause_after_speech_finalizes_utterance(streaming_config: StreamingConfig) -> None:
    vad = ScriptedVAD([True, True, False])
    stt = FakeSTT(text="turn the lights on")
    transcriber = StreamingTranscriber(stt=stt, vad=vad, config=streaming_config)

    assert transcriber.feed(make_chunk(0.3)) is None
    assert transcriber.feed(make_chunk(0.3)) is None
    result = transcriber.feed(make_chunk(0.5))  # silence >= pause_duration_seconds (0.5)

    assert result is not None
    assert result.text == "turn the lights on"
    assert result.is_final is True
    assert len(stt.calls) == 1
    # the finalized audio covers all three chunks (0.3 + 0.3 + 0.5 = 1.1s)
    assert len(stt.calls[0].data) == int(1.1 * 16000) * 2

    transcriber.close()


def test_max_utterance_duration_forces_finalize_without_a_pause() -> None:
    config = StreamingConfig(
        pause_duration_seconds=0.5,
        max_utterance_seconds=3.0,
        partial_interval_seconds=100.0,  # effectively disabled, isolates this test
        no_speech_timeout_seconds=100.0,
        inference_timeout_seconds=1.0,
    )
    vad = ScriptedVAD([], default=True)  # continuous, uninterrupted speech
    stt = FakeSTT()
    transcriber = StreamingTranscriber(stt=stt, vad=vad, config=config)

    results = [transcriber.feed(make_chunk(1.0)) for _ in range(3)]

    assert results[:2] == [None, None]
    assert results[2] is not None  # 3.0s buffered speech >= max_utterance_seconds
    assert len(stt.calls) == 1

    transcriber.close()


def test_no_speech_timeout_raises(streaming_config: StreamingConfig) -> None:
    vad = ScriptedVAD([], default=False)  # never speech
    transcriber = StreamingTranscriber(stt=FakeSTT(), vad=vad, config=streaming_config)

    try:
        transcriber.feed(make_chunk(2.5))  # >= no_speech_timeout_seconds (2.0)
        raised = False
    except NoSpeechTimeoutError:
        raised = True

    assert raised is True
    transcriber.close()


def test_no_speech_timeout_publishes_error_event(streaming_config: StreamingConfig) -> None:
    events = EventBus()
    received = []
    events.subscribe(VoiceEvents.ERROR, received.append)
    vad = ScriptedVAD([], default=False)
    transcriber = StreamingTranscriber(
        stt=FakeSTT(), vad=vad, config=streaming_config, events=events
    )

    try:
        transcriber.feed(make_chunk(2.5))
    except NoSpeechTimeoutError:
        pass

    assert len(received) == 1
    assert received[0].payload["reason"] == "no_speech_timeout"
    transcriber.close()


def test_partial_result_emitted_via_callback_and_event() -> None:
    config = StreamingConfig(
        pause_duration_seconds=100.0,  # disabled, isolates this test
        max_utterance_seconds=100.0,
        partial_interval_seconds=1.0,
        no_speech_timeout_seconds=100.0,
        inference_timeout_seconds=1.0,
    )
    events = EventBus()
    received_events = []
    events.subscribe(VoiceEvents.PARTIAL_TRANSCRIPT, received_events.append)
    partials = []

    vad = ScriptedVAD([], default=True)
    stt = FakeSTT(text="partial so far")
    transcriber = StreamingTranscriber(
        stt=stt, vad=vad, config=config, events=events, on_partial=partials.append
    )

    result = transcriber.feed(make_chunk(0.6))
    assert result is None
    assert partials == []  # 0.6s < partial_interval_seconds (1.0)

    result = transcriber.feed(make_chunk(0.5))  # cumulative 1.1s >= 1.0
    assert result is None  # partials never come back from feed() itself
    assert len(partials) == 1
    assert partials[0].text == "partial so far"
    assert partials[0].is_final is False
    assert len(received_events) == 1

    transcriber.close()


def test_inference_timeout_during_finalize_raises() -> None:
    config = StreamingConfig(
        pause_duration_seconds=0.2,
        inference_timeout_seconds=0.05,
    )
    vad = ScriptedVAD([True, False])
    stt = FakeSTT(delay=0.3)  # much slower than inference_timeout_seconds
    transcriber = StreamingTranscriber(stt=stt, vad=vad, config=config)

    transcriber.feed(make_chunk(0.3))
    try:
        transcriber.feed(make_chunk(0.2))  # triggers finalize -> slow transcribe -> timeout
        raised = False
    except TranscriptionTimeoutError:
        raised = True

    assert raised is True
    transcriber.close()


def test_inference_timeout_during_partial_is_swallowed_not_raised() -> None:
    config = StreamingConfig(
        pause_duration_seconds=100.0,
        partial_interval_seconds=0.2,
        inference_timeout_seconds=0.05,
        no_speech_timeout_seconds=100.0,
    )
    vad = ScriptedVAD([], default=True)
    stt = FakeSTT(delay=0.3)
    partials = []
    transcriber = StreamingTranscriber(stt=stt, vad=vad, config=config, on_partial=partials.append)

    result = transcriber.feed(make_chunk(0.3))  # crosses partial_interval, but STT is slow

    assert result is None  # no exception propagates out of feed()
    assert partials == []  # the timed-out partial was skipped, not delivered

    transcriber.close()


def test_state_resets_after_finalize_so_next_utterance_is_independent(
    streaming_config: StreamingConfig,
) -> None:
    vad = ScriptedVAD([True, False, True, False])
    stt = FakeSTT()
    transcriber = StreamingTranscriber(stt=stt, vad=vad, config=streaming_config)

    transcriber.feed(make_chunk(0.3))
    first = transcriber.feed(make_chunk(0.5))
    assert first is not None

    transcriber.feed(make_chunk(0.2))
    second = transcriber.feed(make_chunk(0.5))
    assert second is not None

    assert len(stt.calls) == 2
    assert len(stt.calls[0].data) != len(stt.calls[1].data)  # independent buffers
    transcriber.close()


def test_explicit_start_discards_buffered_audio(streaming_config: StreamingConfig) -> None:
    vad = ScriptedVAD([], default=True)
    stt = FakeSTT()
    transcriber = StreamingTranscriber(stt=stt, vad=vad, config=streaming_config)

    transcriber.feed(make_chunk(0.3))
    transcriber.start()  # discard the in-progress utterance
    transcriber.close()

    assert len(stt.calls) == 0


def test_close_without_any_feed_calls_does_not_raise(streaming_config: StreamingConfig) -> None:
    transcriber = StreamingTranscriber(
        stt=FakeSTT(), vad=ScriptedVAD([], default=False), config=streaming_config
    )
    transcriber.close()  # must not raise


def test_force_finalize_returns_buffered_audio_without_waiting_for_a_pause(
    streaming_config: StreamingConfig,
) -> None:
    vad = ScriptedVAD([True])
    stt = FakeSTT(text="turn the lights on")
    transcriber = StreamingTranscriber(stt=stt, vad=vad, config=streaming_config)

    assert transcriber.feed(make_chunk(0.2)) is None  # still speaking, no pause yet
    result = transcriber.force_finalize()

    assert result is not None
    assert result.text == "turn the lights on"
    transcriber.close()


def test_force_finalize_with_nothing_buffered_returns_none(
    streaming_config: StreamingConfig,
) -> None:
    transcriber = StreamingTranscriber(
        stt=FakeSTT(), vad=ScriptedVAD([], default=False), config=streaming_config
    )
    assert transcriber.force_finalize() is None
    transcriber.close()
