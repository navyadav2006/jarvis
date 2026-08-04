from __future__ import annotations

from jarvis.core.voice.ports import (
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
from jarvis.core.voice.types import AudioChunk


def _chunk() -> AudioChunk:
    return AudioChunk(data=b"\x00\x00", sample_rate=16000)


def test_null_microphone_satisfies_protocol() -> None:
    assert isinstance(NullMicrophonePort(), MicrophonePort)


def test_null_wake_word_satisfies_protocol() -> None:
    assert isinstance(NullWakeWordPort(), WakeWordPort)


def test_null_vad_satisfies_protocol() -> None:
    assert isinstance(NullVoiceActivityDetector(), VoiceActivityDetector)


def test_null_stt_satisfies_protocol() -> None:
    assert isinstance(NullSpeechToTextPort(), SpeechToTextPort)


def test_null_tts_satisfies_protocol() -> None:
    assert isinstance(NullTextToSpeechPort(), TextToSpeechPort)


def test_null_player_satisfies_protocol() -> None:
    assert isinstance(NullAudioPlayerPort(), AudioPlayerPort)


def test_null_microphone_start_stop_toggles_is_active() -> None:
    mic = NullMicrophonePort()
    assert mic.is_active is False
    mic.start()
    assert mic.is_active is True
    mic.stop()
    assert mic.is_active is False


def test_null_microphone_read_returns_none_immediately() -> None:
    mic = NullMicrophonePort()
    mic.start()
    assert mic.read(timeout=5.0) is None


def test_null_wake_word_never_detects_anything() -> None:
    port = NullWakeWordPort()
    assert port.process(_chunk()) is None
    port.reset()  # must not raise


def test_null_vad_never_detects_speech() -> None:
    assert NullVoiceActivityDetector().is_speech(_chunk()) is False


def test_null_stt_returns_empty_zero_confidence_transcription() -> None:
    result = NullSpeechToTextPort().transcribe(_chunk())
    assert result.text == ""
    assert result.confidence == 0.0
    assert result.is_final is True


def test_null_tts_returns_silence() -> None:
    audio = NullTextToSpeechPort().synthesize("hello")
    assert audio.data == b""
    assert audio.sample_rate == 16000


def test_null_player_never_reports_playing() -> None:
    player = NullAudioPlayerPort()
    assert player.is_playing is False
    player.play(_chunk())
    assert player.is_playing is False
    player.stop()  # must not raise even though nothing was playing
    assert player.is_playing is False
