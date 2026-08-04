from __future__ import annotations

import queue
import threading
import time

import pytest

from jarvis.core.config.voice_config import SpeechQueueConfig, StreamingConfig
from jarvis.core.voice.types import AudioChunk, TranscriptionResult

SAMPLE_RATE = 16000


def make_chunk(
    seconds: float, *, sample_rate: int = SAMPLE_RATE, marker: bytes = b"\x00\x00"
) -> AudioChunk:
    """A chunk of `seconds` duration at 16-bit mono PCM, filled with `marker`."""
    num_samples = max(1, round(seconds * sample_rate))
    return AudioChunk(
        data=marker * num_samples, sample_rate=sample_rate, channels=1, sample_width=2
    )


class ScriptedVAD:
    """A VoiceActivityDetector whose answers are pre-scripted by the test,
    one bool per feed() call, consumed in order; once the script runs
    out, `default` is returned for every subsequent call.
    """

    def __init__(self, script: list[bool], *, default: bool = False) -> None:
        self._script = list(script)
        self._default = default
        self.calls = 0

    def is_speech(self, chunk: AudioChunk) -> bool:
        self.calls += 1
        if self._script:
            return self._script.pop(0)
        return self._default


class FakeSTT:
    """A SpeechToTextPort whose transcribe() returns a fixed result (and
    optionally sleeps first, to exercise inference-timeout handling).
    """

    def __init__(
        self, *, text: str = "hello world", language: str = "en", delay: float = 0.0
    ) -> None:
        self.text = text
        self.language = language
        self.delay = delay
        self.calls: list[AudioChunk] = []

    def transcribe(self, audio: AudioChunk) -> TranscriptionResult:
        self.calls.append(audio)
        if self.delay:
            time.sleep(self.delay)
        return TranscriptionResult(text=self.text, is_final=True, language=self.language)


@pytest.fixture
def streaming_config() -> StreamingConfig:
    return StreamingConfig(
        pause_duration_seconds=0.5,
        max_utterance_seconds=5.0,
        no_speech_timeout_seconds=2.0,
        partial_interval_seconds=1.0,
        inference_timeout_seconds=1.0,
    )


class FakeTTS:
    """A TextToSpeechPort that returns a fixed-duration chunk of audio,
    optionally raising for specific input text (to exercise
    SpeechQueue's synthesis-failure handling).
    """

    def __init__(self, *, audio_seconds: float = 0.05, fail_on: set[str] | None = None) -> None:
        self.audio_seconds = audio_seconds
        self.fail_on = fail_on or set()
        self.calls: list[str] = []

    def synthesize(self, text: str) -> AudioChunk:
        self.calls.append(text)
        if text in self.fail_on:
            raise RuntimeError(f"synthesis failed for {text!r}")
        return make_chunk(self.audio_seconds, marker=b"\x10\x00")


class FakeAudioPlayerPort:
    """An AudioPlayerPort that simulates playback finishing after
    `play_seconds` (via a background timer, not a real audio device),
    so tests can exercise SpeechQueue's polling loop, skip(), and
    interrupt() against realistic play()/stop()/is_playing timing
    without any real audio hardware.
    """

    def __init__(self, *, play_seconds: float = 0.05) -> None:
        self.play_seconds = play_seconds
        self.played: list[AudioChunk] = []
        self.stop_calls = 0
        self._playing = False
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def play(self, audio: AudioChunk) -> None:
        self.played.append(audio)
        with self._lock:
            self._playing = True
            self._timer = threading.Timer(self.play_seconds, self._finish)
            self._timer.daemon = True
            self._timer.start()

    def _finish(self) -> None:
        with self._lock:
            self._playing = False

    def stop(self) -> None:
        self.stop_calls += 1
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._playing = False

    @property
    def is_playing(self) -> bool:
        with self._lock:
            return self._playing


@pytest.fixture
def queue_config() -> SpeechQueueConfig:
    return SpeechQueueConfig(max_queue_size=None, poll_interval_seconds=0.01)


class QueueMicrophonePort:
    """A MicrophonePort whose read() drains a queue the test pushes
    chunks into — lets a test drive JarvisVoicePipeline's background
    audio-loop thread deterministically without real audio hardware.
    """

    def __init__(self) -> None:
        self._queue: queue.Queue = queue.Queue()
        self._active = False

    def start(self) -> None:
        self._active = True

    def stop(self) -> None:
        self._active = False

    def read(self, timeout: float | None = None) -> AudioChunk | None:
        try:
            return self._queue.get(timeout=timeout or 0.05)
        except queue.Empty:
            return None

    def push(self, chunk: AudioChunk) -> None:
        self._queue.put(chunk)

    @property
    def is_active(self) -> bool:
        return self._active


class ToggleVAD:
    """A VoiceActivityDetector whose answer is settable at any time
    (`vad.speech = True/False`), rather than a consumed script — needed
    for pipeline tests, where is_speech() is called from more than one
    call site (StreamingTranscriber during LISTENING, the audio loop's
    barge-in check during SPEAKING) in an order the test doesn't fully
    control.
    """

    def __init__(self, *, speech: bool = False) -> None:
        self.speech = speech
        self.calls = 0

    def is_speech(self, chunk: AudioChunk) -> bool:
        self.calls += 1
        return self.speech


class ScriptedWakeWord:
    """A WakeWordPort that fires once process() has been called
    `trigger_after` times, then never again until reset().
    """

    def __init__(self, *, trigger_after: int = 1, name: str = "hey_jarvis") -> None:
        self.trigger_after = trigger_after
        self.name = name
        self.calls = 0
        self.reset_calls = 0

    def process(self, chunk: AudioChunk) -> str | None:
        self.calls += 1
        if self.calls >= self.trigger_after:
            return self.name
        return None

    def reset(self) -> None:
        self.reset_calls += 1


class FakeAssistant:
    """An AssistantHandler stand-in for Orchestrator.handle(...).text."""

    def __init__(self, response: str = "ok") -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []

    def __call__(self, text: str, session_id: str) -> str:
        self.calls.append((text, session_id))
        return self.response
