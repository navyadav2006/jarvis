from __future__ import annotations

import sys
import time
import types
from typing import Any

import pytest

from jarvis.core.config.voice_config import AudioPlayerConfig, MicrophoneConfig
from jarvis.core.exceptions import SpeechBackendUnavailableError
from jarvis.core.speech.sounddevice_io import SoundDeviceAudioPlayer, SoundDeviceMicrophone
from jarvis.core.voice.types import AudioChunk

from .conftest import make_chunk


class FakeInputStream:
    """Stands in for sounddevice.InputStream: records the callback it was
    given so a test can invoke it directly, instead of needing real
    PortAudio hardware to actually produce audio.
    """

    instances: list["FakeInputStream"] = []

    def __init__(self, *, samplerate: int, channels: int, dtype: str, blocksize: int,
                 device: Any, callback: Any) -> None:
        self.samplerate = samplerate
        self.channels = channels
        self.dtype = dtype
        self.blocksize = blocksize
        self.device = device
        self.callback = callback
        self.started = False
        self.closed = False
        FakeInputStream.instances.append(self)

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.started = False

    def close(self) -> None:
        self.closed = True


def _make_fake_sounddevice(*, wait_seconds: float = 0.0) -> types.SimpleNamespace:
    state = {"playing": False}

    def play(samples: Any, samplerate: int, device: Any = None) -> None:
        state["playing"] = True
        state["last_samples"] = samples
        state["last_samplerate"] = samplerate

    def stop() -> None:
        state["playing"] = False

    def wait() -> None:
        if wait_seconds:
            time.sleep(wait_seconds)

    return types.SimpleNamespace(
        InputStream=FakeInputStream, play=play, stop=stop, wait=wait, _state=state
    )


@pytest.fixture(autouse=True)
def _reset_fake_input_stream_instances() -> None:
    FakeInputStream.instances.clear()
    yield
    FakeInputStream.instances.clear()


# -- SoundDeviceMicrophone -------------------------------------------------


def test_microphone_construction_never_requires_backend() -> None:
    SoundDeviceMicrophone(MicrophoneConfig())  # must not raise, no import triggered


def test_microphone_start_raises_clear_error_when_backend_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "sounddevice", None)
    mic = SoundDeviceMicrophone(MicrophoneConfig())
    with pytest.raises(SpeechBackendUnavailableError, match="sounddevice is not installed"):
        mic.start()


def test_microphone_start_opens_stream_and_read_drains_callback_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_sd = _make_fake_sounddevice()
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sd)

    mic = SoundDeviceMicrophone(MicrophoneConfig(sample_rate=16000, channels=1, block_size=160))
    mic.start()
    assert mic.is_active is True
    assert len(FakeInputStream.instances) == 1
    stream = FakeInputStream.instances[0]
    assert stream.started is True

    # Simulate PortAudio invoking the callback on its own thread.
    stream.callback(b"\x01\x02" * 80, 160, None, None)

    chunk = mic.read(timeout=1.0)
    assert chunk is not None
    assert chunk.data == b"\x01\x02" * 80
    assert chunk.sample_rate == 16000
    assert chunk.channels == 1
    assert chunk.sample_width == 2


def test_microphone_read_returns_none_on_empty_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_sd = _make_fake_sounddevice()
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sd)
    mic = SoundDeviceMicrophone(MicrophoneConfig())
    mic.start()
    assert mic.read(timeout=0.01) is None


def test_microphone_stop_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_sd = _make_fake_sounddevice()
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sd)
    mic = SoundDeviceMicrophone(MicrophoneConfig())
    mic.start()
    mic.stop()
    mic.stop()  # must not raise
    assert mic.is_active is False
    assert FakeInputStream.instances[0].closed is True


def test_microphone_queue_drops_oldest_chunk_when_full(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_sd = _make_fake_sounddevice()
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sd)
    mic = SoundDeviceMicrophone(MicrophoneConfig(queue_size=1))
    mic.start()
    stream = FakeInputStream.instances[0]

    stream.callback(b"\x01\x01", 1, None, None)
    stream.callback(b"\x02\x02", 1, None, None)  # queue is full: drops the first

    chunk = mic.read(timeout=1.0)
    assert chunk is not None
    assert chunk.data == b"\x02\x02"
    assert mic.read(timeout=0.01) is None


# -- SoundDeviceAudioPlayer -------------------------------------------------


def test_player_construction_never_requires_backend() -> None:
    SoundDeviceAudioPlayer(AudioPlayerConfig())  # must not raise


def test_player_play_raises_clear_error_when_backend_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "sounddevice", None)
    player = SoundDeviceAudioPlayer(AudioPlayerConfig())
    with pytest.raises(SpeechBackendUnavailableError, match="sounddevice is not installed"):
        player.play(make_chunk(0.1))


def test_player_play_empty_chunk_is_a_noop_even_without_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "sounddevice", None)
    player = SoundDeviceAudioPlayer(AudioPlayerConfig())
    player.play(AudioChunk(data=b"", sample_rate=16000))  # must not raise/import
    assert player.is_playing is False


def test_player_play_sets_is_playing_then_wait_thread_clears_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("numpy")
    fake_sd = _make_fake_sounddevice(wait_seconds=0.05)
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sd)
    player = SoundDeviceAudioPlayer(AudioPlayerConfig())

    player.play(make_chunk(0.1))
    assert player.is_playing is True

    deadline = time.monotonic() + 2.0
    while player.is_playing and time.monotonic() < deadline:
        time.sleep(0.01)
    assert player.is_playing is False


def test_player_stop_is_thread_safe_and_clears_playing(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("numpy")
    fake_sd = _make_fake_sounddevice(wait_seconds=5.0)  # long enough that stop() wins the race
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sd)
    player = SoundDeviceAudioPlayer(AudioPlayerConfig())

    player.play(make_chunk(0.1))
    assert player.is_playing is True
    player.stop()
    assert player.is_playing is False
