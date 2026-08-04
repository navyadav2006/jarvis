from __future__ import annotations

import pytest
from pydantic import ValidationError

from jarvis.core.config.voice_config import (
    AudioPlayerConfig,
    ListeningConfig,
    ListeningMode,
    MicrophoneConfig,
    SpeechQueueConfig,
    StreamingConfig,
    TextToSpeechConfig,
    VoiceConfig,
    WakeWordConfig,
)


def test_voice_disabled_by_default() -> None:
    assert VoiceConfig().enabled is False


def test_wake_word_threshold_within_range_is_valid() -> None:
    assert WakeWordConfig(threshold=0.3).threshold == 0.3


def test_wake_word_defaults() -> None:
    wake_word = VoiceConfig().wake_word
    assert wake_word.models == ["hey_jarvis"]
    assert wake_word.cooldown_seconds == 2.0
    assert wake_word.inference_framework == "onnx"


def test_wake_word_accepts_multiple_custom_models() -> None:
    wake_word = WakeWordConfig.model_validate(
        {"models": ["hey_jarvis", "data/models/openwakeword/custom.onnx"]}
    )
    assert wake_word.models == ["hey_jarvis", "data/models/openwakeword/custom.onnx"]


def test_wake_word_cooldown_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        WakeWordConfig(cooldown_seconds=0)


def test_wake_word_rejects_unsupported_inference_framework() -> None:
    with pytest.raises(ValidationError):
        WakeWordConfig.model_validate({"inference_framework": "tensorrt"})


def test_wake_word_is_frozen() -> None:
    wake_word = WakeWordConfig()
    with pytest.raises(ValidationError):
        wake_word.threshold = 0.9  # type: ignore[misc]


def test_wake_word_threshold_above_one_is_rejected() -> None:
    with pytest.raises(ValidationError):
        WakeWordConfig(threshold=1.5)


def test_wake_word_threshold_below_zero_is_rejected() -> None:
    with pytest.raises(ValidationError):
        WakeWordConfig(threshold=-0.1)


def test_unsupported_stt_engine_is_rejected() -> None:
    with pytest.raises(ValidationError):
        VoiceConfig.model_validate({"stt": {"engine": "google-cloud"}})


def test_unsupported_tts_engine_is_rejected() -> None:
    with pytest.raises(ValidationError):
        VoiceConfig.model_validate({"tts": {"engine": "azure"}})


def test_listening_defaults_to_push_to_talk_no_conversation_no_background() -> None:
    listening = VoiceConfig().listening
    assert listening.mode == ListeningMode.PUSH_TO_TALK
    assert listening.background is False
    assert listening.conversation_mode is False
    assert listening.allow_interruption is True


def test_listening_mode_accepts_continuous() -> None:
    config = ListeningConfig.model_validate({"mode": "continuous"})
    assert config.mode == ListeningMode.CONTINUOUS


def test_listening_mode_rejects_unknown_value() -> None:
    with pytest.raises(ValidationError):
        ListeningConfig.model_validate({"mode": "wake_word"})


def test_conversation_timeout_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        ListeningConfig(conversation_timeout_seconds=0)


def test_listening_is_frozen() -> None:
    listening = ListeningConfig()
    with pytest.raises(ValidationError):
        listening.background = True  # type: ignore[misc]


def test_voice_config_listening_round_trips_from_yaml_shaped_dict() -> None:
    config = VoiceConfig.model_validate(
        {
            "listening": {
                "mode": "continuous",
                "background": True,
                "conversation_mode": True,
                "conversation_timeout_seconds": 12.0,
                "allow_interruption": False,
            }
        }
    )
    assert config.listening.mode == ListeningMode.CONTINUOUS
    assert config.listening.background is True
    assert config.listening.conversation_mode is True
    assert config.listening.conversation_timeout_seconds == 12.0
    assert config.listening.allow_interruption is False


def test_streaming_defaults() -> None:
    streaming = VoiceConfig().streaming
    assert streaming.pause_duration_seconds == 0.8
    assert streaming.max_utterance_seconds == 30.0
    assert streaming.no_speech_timeout_seconds == 10.0
    assert streaming.partial_interval_seconds == 1.5
    assert streaming.inference_timeout_seconds == 15.0
    assert streaming.vad_aggressiveness == 2


@pytest.mark.parametrize(
    "field",
    [
        "pause_duration_seconds",
        "max_utterance_seconds",
        "no_speech_timeout_seconds",
        "partial_interval_seconds",
        "inference_timeout_seconds",
    ],
)
def test_streaming_durations_must_be_positive(field: str) -> None:
    with pytest.raises(ValidationError):
        StreamingConfig.model_validate({field: 0})


@pytest.mark.parametrize("aggressiveness", [-1, 4])
def test_streaming_vad_aggressiveness_out_of_range_is_rejected(aggressiveness: int) -> None:
    with pytest.raises(ValidationError):
        StreamingConfig(vad_aggressiveness=aggressiveness)


def test_streaming_is_frozen() -> None:
    streaming = StreamingConfig()
    with pytest.raises(ValidationError):
        streaming.pause_duration_seconds = 5.0  # type: ignore[misc]


def test_tts_speed_and_volume_default_to_normal() -> None:
    tts = VoiceConfig().tts
    assert tts.speed == 1.0
    assert tts.volume == 1.0


def test_tts_speed_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        TextToSpeechConfig(speed=0)


def test_tts_volume_cannot_be_negative() -> None:
    with pytest.raises(ValidationError):
        TextToSpeechConfig(volume=-0.1)


def test_tts_volume_may_exceed_one_for_amplification() -> None:
    assert TextToSpeechConfig(volume=1.5).volume == 1.5


def test_queue_defaults() -> None:
    queue = VoiceConfig().queue
    assert queue.max_queue_size is None
    assert queue.poll_interval_seconds == 0.05


def test_queue_max_size_must_be_positive_when_set() -> None:
    with pytest.raises(ValidationError):
        SpeechQueueConfig(max_queue_size=0)


def test_queue_poll_interval_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        SpeechQueueConfig(poll_interval_seconds=0)


def test_queue_is_frozen() -> None:
    queue = SpeechQueueConfig()
    with pytest.raises(ValidationError):
        queue.max_queue_size = 5  # type: ignore[misc]


def test_mic_defaults() -> None:
    mic = VoiceConfig().mic
    assert mic.device is None
    assert mic.sample_rate == 16000
    assert mic.channels == 1
    assert mic.block_size == 320
    assert mic.queue_size == 50


def test_mic_accepts_int_or_str_device() -> None:
    assert MicrophoneConfig(device=2).device == 2
    assert MicrophoneConfig(device="USB Mic").device == "USB Mic"


def test_mic_block_size_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        MicrophoneConfig(block_size=0)


def test_mic_block_size_accepts_10_20_30ms_frames_at_16khz() -> None:
    assert MicrophoneConfig(sample_rate=16000, block_size=160).block_size == 160  # 10ms
    assert MicrophoneConfig(sample_rate=16000, block_size=320).block_size == 320  # 20ms
    assert MicrophoneConfig(sample_rate=16000, block_size=480).block_size == 480  # 30ms


def test_mic_block_size_rejects_non_vad_legal_frame_duration() -> None:
    # This is the exact real-world bug: 1600 samples at 16kHz is a
    # 100ms frame, which WebRtcVoiceActivityDetector rejects mid-
    # conversation — now caught at config-construction time instead.
    with pytest.raises(ValidationError, match="10, 20, or 30ms"):
        MicrophoneConfig(sample_rate=16000, block_size=1600)


def test_mic_block_size_scales_with_sample_rate() -> None:
    assert MicrophoneConfig(sample_rate=32000, block_size=640).block_size == 640  # 20ms @ 32kHz
    with pytest.raises(ValidationError):
        MicrophoneConfig(sample_rate=32000, block_size=500)  # 15.625ms @ 32kHz — not legal


def test_mic_queue_size_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        MicrophoneConfig(queue_size=0)


def test_mic_is_frozen() -> None:
    mic = MicrophoneConfig()
    with pytest.raises(ValidationError):
        mic.sample_rate = 8000  # type: ignore[misc]


def test_player_device_defaults_to_none() -> None:
    assert VoiceConfig().player.device is None


def test_player_accepts_int_or_str_device() -> None:
    assert AudioPlayerConfig(device=1).device == 1
    assert AudioPlayerConfig(device="Speakers").device == "Speakers"


def test_player_is_frozen() -> None:
    player = AudioPlayerConfig()
    with pytest.raises(ValidationError):
        player.device = 3  # type: ignore[misc]
