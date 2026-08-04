"""SoundDeviceMicrophone/SoundDeviceAudioPlayer: real MicrophonePort/
AudioPlayerPort implementations (core/voice/ports.py's Phase 5
interfaces) backed by the `sounddevice` library (PortAudio bindings).

sounddevice was chosen over pyaudio for the same "avoid a painful
native build step" reasoning as pywhispercpp/piper-tts/openwakeword
elsewhere in this package: it ships prebuilt wheels (including on
Windows) with no PortAudio compilation required. See
docs/architecture.md's voice-wiring section for the alternatives
considered.

Both classes lazy-import `sounddevice` inside `start()`/`play()`
respectively, not at module load time — matching every other real
speech backend in this package (WhisperCppSpeechToText,
OpenWakeWordDetector, PiperTextToSpeech, WebRtcVoiceActivityDetector).
Constructing either class, and importing jarvis.core.speech generally,
never requires sounddevice to be installed.

NOTE: sounddevice's callback-stream API was implemented against its
documented shape, not verified against a locally installed copy in
this environment — same unverified-API caveat every other real speech
backend in this package already carries.
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Any

from jarvis.core.config.voice_config import AudioPlayerConfig, MicrophoneConfig
from jarvis.core.exceptions import SpeechBackendUnavailableError
from jarvis.core.voice.types import AudioChunk

logger = logging.getLogger(__name__)

_SAMPLE_WIDTH_BYTES = 2  # 16-bit PCM, matching AudioChunk's default/whisper.cpp/webrtcvad


def _import_sounddevice() -> Any:
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise SpeechBackendUnavailableError(
            "sounddevice is not installed; install the 'voice' extra "
            "(pip install -e '.[voice]') to use SoundDeviceMicrophone/SoundDeviceAudioPlayer"
        ) from exc
    return sd


class SoundDeviceMicrophone:
    """Implements core.voice.ports.MicrophonePort.

    Captures audio on sounddevice's own callback thread and hands each
    block to a bounded queue.Queue; `read()` just drains that queue, so
    the actual PortAudio callback (which must never block or do slow
    work) stays a single `queue.put_nowait()`. A full queue drops the
    oldest pending chunk rather than blocking the audio callback or
    raising — a background voice pipeline that's fallen behind should
    lose old audio, not stall real-time capture further.
    """

    def __init__(self, config: MicrophoneConfig) -> None:
        self._config = config
        self._stream: Any = None
        self._queue: queue.Queue[AudioChunk] = queue.Queue(maxsize=config.queue_size)
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self._stream is not None:
                return
            sd = _import_sounddevice()
            self._stream = sd.InputStream(
                samplerate=self._config.sample_rate,
                channels=self._config.channels,
                dtype="int16",
                blocksize=self._config.block_size,
                device=self._config.device,
                callback=self._on_audio,
            )
            self._stream.start()

    def stop(self) -> None:
        with self._lock:
            if self._stream is None:
                return
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def read(self, timeout: float | None = None) -> AudioChunk | None:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._stream is not None

    def _on_audio(self, indata: Any, frames: int, time_info: Any, status: Any) -> None:
        # Called on PortAudio's own thread — must stay fast and must
        # never raise, or sounddevice tears the stream down.
        if status:
            logger.debug("SoundDeviceMicrophone input status: %s", status)
        chunk = AudioChunk(
            data=bytes(indata),
            sample_rate=self._config.sample_rate,
            channels=self._config.channels,
            sample_width=_SAMPLE_WIDTH_BYTES,
        )
        try:
            self._queue.put_nowait(chunk)
        except queue.Full:
            try:
                self._queue.get_nowait()  # drop oldest, make room
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(chunk)
            except queue.Full:
                pass  # lost this chunk under sustained overload; acceptable


class SoundDeviceAudioPlayer:
    """Implements core.voice.ports.AudioPlayerPort.

    Plays whatever sample rate/channel count each AudioChunk itself
    reports (TTS output format is a synthesis-time concern owned by
    the TextToSpeechPort backend, not this player — see AudioChunk's
    docstring) rather than assuming a fixed configured rate.

    `play()`/`stop()`/`is_playing` are all just thin wrappers over
    sounddevice's module-level `play`/`stop`/`get_stream()` calls,
    which are themselves safe to call from any thread — satisfying
    AudioPlayerPort's thread-safety contract (stop()/is_playing must
    be callable from a different thread than play(), for barge-in).
    """

    def __init__(self, config: AudioPlayerConfig) -> None:
        self._config = config
        self._playing = False
        self._lock = threading.Lock()

    def play(self, audio: AudioChunk) -> None:
        if not audio.data:
            return
        sd = _import_sounddevice()
        samples = _pcm16_bytes_to_int16_array(audio.data, audio.channels)
        with self._lock:
            self._playing = True
        sd.play(samples, samplerate=audio.sample_rate, device=self._config.device)
        threading.Thread(target=self._wait_until_finished, args=(sd,), daemon=True).start()

    def stop(self) -> None:
        sd = _import_sounddevice()
        sd.stop()
        with self._lock:
            self._playing = False

    @property
    def is_playing(self) -> bool:
        with self._lock:
            return self._playing

    def _wait_until_finished(self, sd: Any) -> None:
        # sd.wait() blocks the calling thread (this helper's own daemon
        # thread, never the caller of play()) until playback finishes
        # or sd.stop() is called elsewhere — that's what lets is_playing
        # flip back to False without a polling loop.
        sd.wait()
        with self._lock:
            self._playing = False


def _pcm16_bytes_to_int16_array(data: bytes, channels: int) -> Any:
    try:
        import numpy as np
    except ImportError as exc:
        raise SpeechBackendUnavailableError(
            "numpy is not installed; install the 'voice' extra "
            "(pip install -e '.[voice]') to use SoundDeviceAudioPlayer"
        ) from exc
    samples = np.frombuffer(data, dtype=np.int16)
    if channels > 1:
        samples = samples.reshape(-1, channels)
    return samples
