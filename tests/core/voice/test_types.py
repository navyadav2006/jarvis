from __future__ import annotations

from jarvis.core.voice.types import AudioChunk, TranscriptionResult, VoiceEvents, VoiceState


def test_audio_chunk_defaults() -> None:
    chunk = AudioChunk(data=b"\x00\x01", sample_rate=16000)
    assert chunk.channels == 1
    assert chunk.sample_width == 2
    assert chunk.timestamp is not None


def test_transcription_result_defaults_to_final() -> None:
    result = TranscriptionResult(text="hello")
    assert result.is_final is True
    assert result.confidence is None


def test_voice_state_values_are_strings() -> None:
    assert VoiceState.IDLE.value == "idle"
    assert VoiceState.LISTENING.value == "listening"
    assert VoiceState.SPEAKING.value == "speaking"


def test_voice_events_are_namespaced_strings() -> None:
    assert VoiceEvents.LISTENING_STARTED == "voice.listening_started"
    assert VoiceEvents.INTERRUPTED == "voice.interrupted"
