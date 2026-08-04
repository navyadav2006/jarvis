"""voice.yaml — wake word, speech-to-text, text-to-speech, and
listening-mode settings for the (interfaces-only, see
core/voice/) voice pipeline: OpenWakeWord, Whisper.cpp, Piper TTS.

`enabled: false` by default, and no voice pipeline implementation
exists yet — this schema exists so the shape of voice configuration is
fixed and validated before that implementation is built, the same
pattern used for memory.yaml in Phase 3. Model/voice file paths are
typed as `Path` but not checked for existence here: that belongs to
whatever loads them at runtime, not the config system, since a path
can be legitimately absent until a model is downloaded.

`listening` (added in Phase 5) is the config-level half of "design the
interfaces" for continuous listening / push-to-talk / conversation
mode / background listening / voice interruption: it fixes the shape
of what's configurable about each before core/voice/pipeline.py's
VoicePipeline (the code-level half of that interface) has a concrete
implementation to read it.

`streaming` (added in Phase 6, alongside core/speech/'s real
whisper.cpp integration) configures StreamingTranscriber: how long a
pause counts as the speaker finishing an utterance, how long to wait
before giving up on hearing any speech at all, how often to emit
low-latency partial transcriptions, and how long a single whisper.cpp
call is allowed to run before being treated as hung.

`tts.speed`/`tts.volume` and `queue` (added in Phase 7, alongside
core/speech/'s real Piper integration) configure PiperTextToSpeech and
SpeechQueue respectively: how fast synthesized speech is spoken, the
default playback volume, and how many queued-but-unspoken responses
are allowed to pile up before SpeechQueue.enqueue() refuses more.

`wake_word` (extended in Phase 8, alongside core/speech/'s real
OpenWakeWordDetector) configures which wake word model(s) are loaded,
how confident a detection must be, and how long to suppress repeat
detections of the same word after one fires.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

VOICE_FILENAME = "voice.yaml"


class WakeWordConfig(BaseModel):
    """Tuning for OpenWakeWordDetector (core/speech/wake_word.py, Phase 8)."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = True

    # Each entry is either a built-in openWakeWord model name (e.g.
    # "hey_jarvis") or a filesystem path to a custom-trained .onnx/
    # .tflite model. openWakeWord loads and scores all of them
    # simultaneously, which is what "supports custom wake words" means
    # here: any number of them, built-in or custom, active at once.
    models: list[str] = Field(default_factory=lambda: ["hey_jarvis"])

    threshold: float = Field(0.5, ge=0.0, le=1.0)

    # After a wake word fires, how much *audio* (not wall-clock — see
    # streaming.py's module docstring for why duration-based timing is
    # used throughout the speech module) must be fed before the same
    # model is allowed to fire again. Without this, one sustained
    # utterance of the wake word — or its echo coming back through a
    # speaker — could re-trigger detection many times over.
    cooldown_seconds: float = Field(2.0, gt=0.0)

    # openWakeWord supports both; onnx is the more widely-tested default.
    inference_framework: Literal["onnx", "tflite"] = "onnx"


class SpeechToTextConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    engine: Literal["whisper.cpp"] = "whisper.cpp"
    model_path: Path = Path("data/models/whisper/ggml-base.en.bin")
    # "auto" enables whisper.cpp's own language identification instead of
    # forcing a fixed language — see core/speech/whisper_cpp.py.
    language: str = "en"


class TextToSpeechConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    engine: Literal["piper"] = "piper"
    voice: str = "en_US-lessac-medium"
    model_path: Path = Path("data/models/piper/en_US-lessac-medium.onnx")

    # Speaking rate multiplier: 1.0 = normal, 2.0 = twice as fast, 0.5 =
    # half speed. Mapped to Piper's `length_scale` (inverse of speed) at
    # synthesis time — see core/speech/piper_tts.py. This is a synthesis-
    # time parameter, not a live one: changing it requires resynthesizing,
    # unlike `volume` below, which SpeechQueue can apply after the fact.
    speed: float = Field(1.0, gt=0.0)

    # Default playback volume multiplier: 1.0 = unchanged, 0.0 = silent,
    # >1.0 = amplified (risking clipping — see core/speech/audio.py's
    # apply_gain()). This is just SpeechQueue's *starting* volume;
    # SpeechQueue.set_volume() changes it at runtime without resynthesizing.
    volume: float = Field(1.0, ge=0.0)


class ListeningMode(StrEnum):
    """How an utterance's start/end is decided. No wake-word member here
    on purpose — wake_word above is a separate, independent gate (once
    implemented) on top of either mode, not a third mode of its own.
    """

    PUSH_TO_TALK = "push_to_talk"
    CONTINUOUS = "continuous"


class ListeningConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    mode: ListeningMode = ListeningMode.PUSH_TO_TALK

    # Background listening: whether a real pipeline should run its
    # listen loop off the main thread/task, so the rest of the app
    # never blocks on audio I/O. A config flag rather than something
    # inferred, since a push-to-talk pipeline can *also* run in the
    # background — the two are independent (see docs/architecture.md's
    # Phase 5 section).
    background: bool = False

    # Conversation mode: after the assistant finishes speaking, keep
    # listening for the next turn automatically instead of requiring a
    # fresh trigger (a push-to-talk press, or — once it exists — a wake
    # word) for every single turn.
    conversation_mode: bool = False
    conversation_timeout_seconds: float = Field(8.0, gt=0.0)

    # Voice interruption (barge-in): whether the user speaking while
    # the assistant is talking stops playback immediately and starts
    # capturing the interruption as the next utterance.
    allow_interruption: bool = True


class StreamingConfig(BaseModel):
    """Tuning for StreamingTranscriber (core/speech/streaming.py).

    Every duration here except `inference_timeout_seconds` is measured
    against the *audio's own* duration, not wall-clock time — see
    streaming.py's module docstring for why.
    """

    model_config = ConfigDict(frozen=True)

    # Consecutive silence (in audio seconds) after speech has started
    # that counts as the speaker pausing — finalizes the utterance.
    pause_duration_seconds: float = Field(0.8, gt=0.0)

    # Hard cap on a single utterance's buffered speech duration, in case
    # the speaker never pauses — forces a finalize rather than buffering
    # forever.
    max_utterance_seconds: float = Field(30.0, gt=0.0)

    # How much audio (with no speech detected at all) to tolerate before
    # giving up on hearing anything and raising NoSpeechTimeoutError.
    no_speech_timeout_seconds: float = Field(10.0, gt=0.0)

    # How much new buffered speech to accumulate between low-latency
    # partial (is_final=False) transcriptions while an utterance is
    # still ongoing.
    partial_interval_seconds: float = Field(1.5, gt=0.0)

    # Wall-clock ceiling on a single whisper.cpp transcribe() call. This
    # one IS real time, not audio time — it bounds actual inference
    # duration, which has no relationship to the audio's length.
    inference_timeout_seconds: float = Field(15.0, gt=0.0)

    # 0 (least aggressive, most permissive) - 3 (most aggressive, most
    # likely to reject borderline audio as noise) — passed to
    # WebRtcVoiceActivityDetector.
    vad_aggressiveness: int = Field(2, ge=0, le=3)


class SpeechQueueConfig(BaseModel):
    """Tuning for SpeechQueue (core/speech/queue.py)."""

    model_config = ConfigDict(frozen=True)

    # None = unbounded. A number gives enqueue() a ceiling, past which it
    # raises SpeechQueueFullError rather than growing forever if nothing
    # is draining the queue (e.g. playback backend stuck/misconfigured).
    max_queue_size: int | None = Field(None, gt=0)

    # How often the worker thread checks AudioPlayerPort.is_playing to
    # notice playback finished and advance to the next queued item.
    poll_interval_seconds: float = Field(0.05, gt=0.0)


class MicrophoneConfig(BaseModel):
    """Tuning for SoundDeviceMicrophone (core/speech/sounddevice_io.py).

    Added alongside the first real MicrophonePort implementation — no
    prior phase needed device/format fields since only Null/test
    doubles existed. 16000/1/16-bit is a fixed requirement, not a
    default to change casually: whisper.cpp, webrtcvad, and
    openWakeWord (Phases 6/8) all expect 16kHz mono 16-bit PCM, and
    nothing in the speech module resamples (see core/speech/audio.py's
    module docstring).

    BUG FIX (Cowork-correction follow-up): `block_size` originally
    defaulted to 1600 (100ms). WebRtcVoiceActivityDetector
    (core/speech/vad.py) requires *exactly* a 10, 20, or 30ms frame per
    `is_speech()` call and raises `SpeechError` on anything else — and
    `JarvisVoicePipeline._audio_loop` feeds whatever size chunk the
    MicrophonePort produces straight into it during LISTENING, with no
    resizing in between. A 100ms chunk crashed the pipeline's one
    background thread the instant the wake word fired and a real
    utterance started — silently, since nothing monitors that thread —
    which looked to a user like "wake word worked, then nothing ever
    happened." OpenWakeWordDetector has no such constraint (it buffers
    internally regardless of chunk size — see its own docstring), so
    20ms is safe for both. Caught by actually saying "hey jarvis" and
    watching the whole pipeline die, not by reading the code.
    """

    model_config = ConfigDict(frozen=True)

    # None = sounddevice's configured default input device. An int
    # (PortAudio device index) or str (substring match against a
    # device name) selects a specific one — see `python -m
    # sounddevice` to list what's available on this machine.
    device: int | str | None = None
    sample_rate: int = 16000
    channels: int = 1
    # Frames per captured block. Must produce a WebRTC-VAD-legal frame
    # duration (10/20/30ms at 16kHz = 160/320/480 samples) — see the
    # class docstring's BUG FIX note. 320 = 20ms, the standard middle
    # ground: low enough for responsive barge-in/wake-word detection,
    # high enough to avoid excessive callback overhead.
    block_size: int = Field(320, gt=0)

    @model_validator(mode="after")
    def _block_size_is_a_legal_vad_frame(self) -> "MicrophoneConfig":
        # Mirrors WebRtcVoiceActivityDetector's own hard requirement
        # (core/speech/vad.py's _VALID_FRAME_MS/_VALID_SAMPLE_RATES) —
        # duplicated here rather than imported, since core/config/ must
        # not depend on core/speech/. This is the config-time half of
        # the fix for the bug documented in the class docstring: catch
        # an incompatible block_size at startup, not mid-conversation
        # when a real utterance first reaches the VAD.
        frame_ms = (self.block_size * 1000) / self.sample_rate
        if round(frame_ms, 6) not in (10.0, 20.0, 30.0):
            raise ValueError(
                f"mic.block_size={self.block_size} at mic.sample_rate={self.sample_rate} "
                f"produces a {frame_ms:g}ms frame, but WebRtcVoiceActivityDetector requires "
                "exactly 10, 20, or 30ms per frame — e.g. block_size=320 for 20ms at 16000Hz"
            )
        return self
    # Bounds SoundDeviceMicrophone's internal queue.Queue — see its
    # docstring for why a full queue drops the oldest chunk rather
    # than blocking the real-time audio callback.
    queue_size: int = Field(50, gt=0)


class AudioPlayerConfig(BaseModel):
    """Tuning for SoundDeviceAudioPlayer (core/speech/sounddevice_io.py)."""

    model_config = ConfigDict(frozen=True)

    # None = sounddevice's configured default output device.
    device: int | str | None = None


class VoiceConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    enabled: bool = False
    wake_word: WakeWordConfig = Field(default_factory=WakeWordConfig)
    stt: SpeechToTextConfig = Field(default_factory=SpeechToTextConfig)
    tts: TextToSpeechConfig = Field(default_factory=TextToSpeechConfig)
    listening: ListeningConfig = Field(default_factory=ListeningConfig)
    streaming: StreamingConfig = Field(default_factory=StreamingConfig)
    queue: SpeechQueueConfig = Field(default_factory=SpeechQueueConfig)
    mic: MicrophoneConfig = Field(default_factory=MicrophoneConfig)
    player: AudioPlayerConfig = Field(default_factory=AudioPlayerConfig)
