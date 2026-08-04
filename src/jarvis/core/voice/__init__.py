"""The voice module: interfaces for a Microphone -> Speech-to-Text ->
Assistant -> Text-to-Speech pipeline supporting continuous listening,
push-to-talk, conversation mode, background listening, and voice
interruption (barge-in). No wake word support yet — see
core/config/voice_config.py's `wake_word` section for the reserved,
not-yet-consumed config, and docs/architecture.md's Phase 5 section
for why.

This phase designs the interfaces only: `ports.py` defines the
Protocol each pipeline stage must satisfy (with Null Object defaults,
same pattern as MemoryPort/AutomationPort/FilesystemPort), and
`pipeline.py` defines VoicePipeline, the abstract contract a concrete
implementation must fulfill. No concrete implementation backed by a
real microphone, Whisper.cpp, or Piper exists yet, and nothing in
main.py or the orchestrator references this package yet — see
docs/architecture.md for the full rationale and what's deferred.
"""

from __future__ import annotations

from jarvis.core.voice.pipeline import VoicePipeline
from jarvis.core.voice.ports import (
    AssistantHandler,
    AudioPlayerPort,
    MicrophonePort,
    NullAudioPlayerPort,
    NullMicrophonePort,
    NullSpeechToTextPort,
    NullTextToSpeechPort,
    NullVoiceActivityDetector,
    NullWakeWordPort,
    SpeechToTextPort,
    TextToSpeechPort,
    VoiceActivityDetector,
    WakeWordPort,
)
from jarvis.core.voice.types import AudioChunk, TranscriptionResult, VoiceEvents, VoiceState

__all__ = [
    "VoicePipeline",
    "AssistantHandler",
    "AudioPlayerPort",
    "MicrophonePort",
    "NullAudioPlayerPort",
    "NullMicrophonePort",
    "NullSpeechToTextPort",
    "NullTextToSpeechPort",
    "NullVoiceActivityDetector",
    "NullWakeWordPort",
    "SpeechToTextPort",
    "TextToSpeechPort",
    "VoiceActivityDetector",
    "WakeWordPort",
    "AudioChunk",
    "TranscriptionResult",
    "VoiceEvents",
    "VoiceState",
]
