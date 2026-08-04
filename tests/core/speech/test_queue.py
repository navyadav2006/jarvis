from __future__ import annotations

import time

import pytest

from jarvis.core.config.voice_config import SpeechQueueConfig
from jarvis.core.events import EventBus
from jarvis.core.exceptions import SpeechQueueFullError
from jarvis.core.speech.queue import SpeechQueue
from jarvis.core.voice.types import VoiceEvents

from .conftest import FakeAudioPlayerPort, FakeTTS


def wait_until(condition, *, timeout: float = 2.0, interval: float = 0.01) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(interval)
    raise AssertionError(f"condition not met within {timeout}s")


@pytest.fixture
def player() -> FakeAudioPlayerPort:
    return FakeAudioPlayerPort(play_seconds=0.05)


@pytest.fixture
def tts() -> FakeTTS:
    return FakeTTS(audio_seconds=0.05)


def test_enqueue_speaks_the_text(
    tts: FakeTTS, player: FakeAudioPlayerPort, queue_config: SpeechQueueConfig
) -> None:
    speech_queue = SpeechQueue(tts=tts, player=player, config=queue_config)
    speech_queue.start()

    speech_queue.enqueue("hello there")
    wait_until(lambda: tts.calls == ["hello there"])
    wait_until(lambda: len(player.played) == 1)

    speech_queue.close()


def test_multiple_enqueued_items_are_spoken_in_order(
    tts: FakeTTS, player: FakeAudioPlayerPort, queue_config: SpeechQueueConfig
) -> None:
    speech_queue = SpeechQueue(tts=tts, player=player, config=queue_config)
    speech_queue.start()

    speech_queue.enqueue("first")
    speech_queue.enqueue("second")
    speech_queue.enqueue("third")

    wait_until(lambda: tts.calls == ["first", "second", "third"])
    speech_queue.close()


def test_pending_count_reflects_unspoken_items(
    tts: FakeTTS, queue_config: SpeechQueueConfig
) -> None:
    # A slow *player* (not a slow TTS — synthesize() is instant; it's
    # is_playing staying True that keeps the worker busy) is what lets
    # the test observe items piling up behind the one currently playing.
    slow_player = FakeAudioPlayerPort(play_seconds=1.0)
    speech_queue = SpeechQueue(tts=tts, player=slow_player, config=queue_config)
    speech_queue.start()

    speech_queue.enqueue("first")
    speech_queue.enqueue("second")
    speech_queue.enqueue("third")

    wait_until(lambda: speech_queue.pending_count == 2)
    speech_queue.close()


def test_skip_stops_current_and_continues_to_next(
    tts: FakeTTS, queue_config: SpeechQueueConfig
) -> None:
    player = FakeAudioPlayerPort(play_seconds=10.0)  # would never finish on its own
    speech_queue = SpeechQueue(tts=tts, player=player, config=queue_config)
    speech_queue.start()

    speech_queue.enqueue("first")
    wait_until(lambda: speech_queue.is_speaking)

    speech_queue.skip()
    speech_queue.enqueue("second")

    wait_until(lambda: tts.calls == ["first", "second"])
    speech_queue.close()


def test_clear_drops_pending_but_lets_current_finish(
    tts: FakeTTS, queue_config: SpeechQueueConfig
) -> None:
    slow_player = FakeAudioPlayerPort(play_seconds=0.3)
    speech_queue = SpeechQueue(tts=tts, player=slow_player, config=queue_config)
    speech_queue.start()

    speech_queue.enqueue("first")
    speech_queue.enqueue("second")
    wait_until(lambda: speech_queue.pending_count == 1)

    speech_queue.clear()
    assert speech_queue.pending_count == 0

    time.sleep(0.5)  # long enough for "first" to finish, if it were going to continue
    assert tts.calls == ["first"]  # "second" was dropped, never synthesized

    speech_queue.close()


def test_interrupt_stops_current_and_drops_pending(
    tts: FakeTTS, queue_config: SpeechQueueConfig
) -> None:
    player = FakeAudioPlayerPort(play_seconds=10.0)
    speech_queue = SpeechQueue(tts=tts, player=player, config=queue_config)
    speech_queue.start()

    speech_queue.enqueue("first")
    speech_queue.enqueue("second")
    wait_until(lambda: speech_queue.is_speaking)

    speech_queue.interrupt()

    assert speech_queue.pending_count == 0
    assert player.stop_calls >= 1
    wait_until(lambda: not speech_queue.is_speaking)
    time.sleep(0.1)
    assert tts.calls == ["first"]  # "second" was dropped, never spoken

    speech_queue.close()


def test_interrupt_publishes_event_with_dropped_count(
    tts: FakeTTS, queue_config: SpeechQueueConfig
) -> None:
    player = FakeAudioPlayerPort(play_seconds=10.0)
    events = EventBus()
    received = []
    events.subscribe(VoiceEvents.INTERRUPTED, received.append)
    speech_queue = SpeechQueue(tts=tts, player=player, config=queue_config, events=events)
    speech_queue.start()

    speech_queue.enqueue("first")
    speech_queue.enqueue("second")
    speech_queue.enqueue("third")
    wait_until(lambda: speech_queue.is_speaking)

    speech_queue.interrupt()

    assert len(received) == 1
    assert received[0].payload["dropped"] == 2
    speech_queue.close()


def test_set_volume_applies_gain_to_played_audio(
    tts: FakeTTS, player: FakeAudioPlayerPort, queue_config: SpeechQueueConfig
) -> None:
    speech_queue = SpeechQueue(tts=tts, player=player, config=queue_config)
    speech_queue.set_volume(0.0)
    speech_queue.start()

    speech_queue.enqueue("hello")
    wait_until(lambda: len(player.played) == 1)

    assert player.played[0].data == b"\x00\x00" * (len(player.played[0].data) // 2)
    speech_queue.close()


def test_set_volume_rejects_negative() -> None:
    speech_queue = SpeechQueue(
        tts=FakeTTS(), player=FakeAudioPlayerPort(), config=SpeechQueueConfig()
    )
    with pytest.raises(ValueError):
        speech_queue.set_volume(-1.0)


def test_max_queue_size_raises_when_full(tts: FakeTTS) -> None:
    config = SpeechQueueConfig(max_queue_size=1, poll_interval_seconds=0.01)
    slow_player = FakeAudioPlayerPort(play_seconds=1.0)
    speech_queue = SpeechQueue(tts=tts, player=slow_player, config=config)
    speech_queue.start()

    speech_queue.enqueue("first")  # picked up immediately by the worker
    wait_until(lambda: speech_queue.is_speaking)
    speech_queue.enqueue("second")  # now queued (pending_count == 1)

    with pytest.raises(SpeechQueueFullError):
        speech_queue.enqueue("third")

    speech_queue.close()


def test_synthesis_failure_is_logged_and_does_not_stop_the_queue(
    player: FakeAudioPlayerPort, queue_config: SpeechQueueConfig
) -> None:
    tts = FakeTTS(fail_on={"bad"})
    events = EventBus()
    received = []
    events.subscribe(VoiceEvents.ERROR, received.append)
    speech_queue = SpeechQueue(tts=tts, player=player, config=queue_config, events=events)
    speech_queue.start()

    speech_queue.enqueue("bad")
    speech_queue.enqueue("good")

    wait_until(lambda: tts.calls == ["bad", "good"])
    wait_until(lambda: len(received) == 1)
    assert received[0].payload["reason"] == "synthesis_failed"
    assert len(player.played) == 1  # only "good" actually reached the player

    speech_queue.close()


def test_close_stops_worker_and_current_playback(
    tts: FakeTTS, queue_config: SpeechQueueConfig
) -> None:
    player = FakeAudioPlayerPort(play_seconds=10.0)
    speech_queue = SpeechQueue(tts=tts, player=player, config=queue_config)
    speech_queue.start()

    speech_queue.enqueue("first")
    wait_until(lambda: speech_queue.is_speaking)

    speech_queue.close()

    assert player.stop_calls >= 1


def test_start_is_idempotent(queue_config: SpeechQueueConfig) -> None:
    speech_queue = SpeechQueue(
        tts=FakeTTS(), player=FakeAudioPlayerPort(), config=queue_config
    )
    speech_queue.start()
    speech_queue.start()  # must not raise or spawn a second worker
    speech_queue.close()


def test_close_without_start_does_not_raise(queue_config: SpeechQueueConfig) -> None:
    speech_queue = SpeechQueue(
        tts=FakeTTS(), player=FakeAudioPlayerPort(), config=queue_config
    )
    speech_queue.close()


def test_initial_volume_is_applied(
    player: FakeAudioPlayerPort, queue_config: SpeechQueueConfig
) -> None:
    speech_queue = SpeechQueue(
        tts=FakeTTS(), player=player, config=queue_config, initial_volume=0.5
    )
    assert speech_queue.volume == 0.5
    speech_queue.close()
