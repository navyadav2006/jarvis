"""The speech module: real wake-word detection (openWakeWord), speech-
to-text (whisper.cpp), and text-to-speech (Piper) engines, plus the
real-time buffering/pause-detection/timeout logic (StreamingTranscriber)
and queueing/interruption/volume logic (SpeechQueue) needed to use them
as a live pipeline.

Deliberately its own package, not folded into core/voice/: everything
here operates purely on AudioChunk streams (core/voice/types.py) and
the SpeechToTextPort/VoiceActivityDetector/TextToSpeechPort/
AudioPlayerPort Protocols (core/voice/ports.py) from Phase 5. As of the
voice-wiring phase, main.py constructs a real JarvisVoicePipeline
(behind voice.yaml's `enabled` flag) from these backends plus
SoundDeviceMicrophone/SoundDeviceAudioPlayer — see
docs/architecture.md's Phase 6 (STT) and Phase 7 (TTS) sections for
history, and the voice-wiring section for how it's actually assembled.

Every optional third-party dependency (openwakeword, pywhispercpp,
webrtcvad, piper-tts, numpy) is imported lazily, inside the method that
needs it, never at module import time — so `import jarvis.core.speech`
always succeeds, and the rest of Jarvis is unaffected by whether the
`voice` extra is installed. StreamingTranscriber and SpeechQueue both
have zero required third-party dependencies at all: they're pure
coordination logic over whatever ports they're given, fully testable
against fakes.
"""

from __future__ import annotations

from jarvis.core.speech.audio import (
    apply_gain,
    chunk_duration_seconds,
    concat_chunks,
    pcm16_bytes_to_float32,
)
from jarvis.core.speech.jarvis_pipeline import JarvisVoicePipeline
from jarvis.core.speech.piper_tts import PiperTextToSpeech
from jarvis.core.speech.queue import SpeechQueue
from jarvis.core.speech.sounddevice_io import SoundDeviceAudioPlayer, SoundDeviceMicrophone
from jarvis.core.speech.streaming import StreamingTranscriber
from jarvis.core.speech.vad import WebRtcVoiceActivityDetector
from jarvis.core.speech.wake_word import OpenWakeWordDetector
from jarvis.core.speech.whisper_cpp import WhisperCppSpeechToText

__all__ = [
    "apply_gain",
    "chunk_duration_seconds",
    "concat_chunks",
    "pcm16_bytes_to_float32",
    "JarvisVoicePipeline",
    "OpenWakeWordDetector",
    "PiperTextToSpeech",
    "SoundDeviceAudioPlayer",
    "SoundDeviceMicrophone",
    "SpeechQueue",
    "StreamingTranscriber",
    "WebRtcVoiceActivityDetector",
    "WhisperCppSpeechToText",
]
