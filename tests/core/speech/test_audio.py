from __future__ import annotations

import array

import pytest

from jarvis.core.exceptions import SpeechError
from jarvis.core.speech.audio import (
    apply_gain,
    chunk_duration_seconds,
    concat_chunks,
    pcm16_bytes_to_float32,
)
from jarvis.core.voice.types import AudioChunk

from .conftest import make_chunk


def test_chunk_duration_seconds_computes_correctly() -> None:
    chunk = make_chunk(0.5)  # 0.5s at 16kHz, 16-bit mono
    assert chunk_duration_seconds(chunk) == pytest.approx(0.5, rel=1e-3)


def test_chunk_duration_seconds_rejects_non_16bit() -> None:
    chunk = AudioChunk(data=b"\x00" * 100, sample_rate=16000, sample_width=1)
    with pytest.raises(SpeechError):
        chunk_duration_seconds(chunk)


def test_concat_chunks_joins_data_in_order() -> None:
    a = make_chunk(0.1, marker=b"\x01\x00")
    b = make_chunk(0.1, marker=b"\x02\x00")
    result = concat_chunks([a, b])
    assert result.data == a.data + b.data
    assert result.sample_rate == a.sample_rate


def test_concat_chunks_empty_list_raises() -> None:
    with pytest.raises(SpeechError):
        concat_chunks([])


def test_concat_chunks_rejects_mismatched_formats() -> None:
    a = make_chunk(0.1, sample_rate=16000)
    b = make_chunk(0.1, sample_rate=8000)
    with pytest.raises(SpeechError):
        concat_chunks([a, b])


def test_pcm16_bytes_to_float32_normalizes_range() -> None:
    np = pytest.importorskip("numpy")
    data = np.array([32767, -32768, 0], dtype=np.int16).tobytes()
    result = pcm16_bytes_to_float32(data)
    assert result[0] == pytest.approx(1.0, abs=1e-4)
    assert result[1] == pytest.approx(-1.0, abs=1e-4)
    assert result[2] == pytest.approx(0.0, abs=1e-4)


def test_pcm16_bytes_to_float32_empty_data() -> None:
    pytest.importorskip("numpy")
    result = pcm16_bytes_to_float32(b"")
    assert len(result) == 0


def _samples(chunk: AudioChunk) -> list[int]:
    arr = array.array("h")
    arr.frombytes(chunk.data)
    return list(arr)


def test_apply_gain_unity_returns_same_object() -> None:
    chunk = make_chunk(0.05)
    assert apply_gain(chunk, 1.0) is chunk


def test_apply_gain_zero_produces_silence() -> None:
    data = array.array("h", [1000, -1000, 500]).tobytes()
    chunk = AudioChunk(data=data, sample_rate=16000, channels=1, sample_width=2)
    result = apply_gain(chunk, 0.0)
    assert _samples(result) == [0, 0, 0]


def test_apply_gain_halves_amplitude() -> None:
    data = array.array("h", [1000, -1000]).tobytes()
    chunk = AudioChunk(data=data, sample_rate=16000, channels=1, sample_width=2)
    result = apply_gain(chunk, 0.5)
    assert _samples(result) == [500, -500]


def test_apply_gain_clamps_instead_of_wrapping_around() -> None:
    data = array.array("h", [30000, -30000]).tobytes()
    chunk = AudioChunk(data=data, sample_rate=16000, channels=1, sample_width=2)
    result = apply_gain(chunk, 2.0)
    samples = _samples(result)
    assert samples == [32767, -32768]  # clamped, not wrapped to a negative/positive value


def test_apply_gain_rejects_negative_gain() -> None:
    with pytest.raises(SpeechError):
        apply_gain(make_chunk(0.05), -0.1)


def test_apply_gain_rejects_non_16bit() -> None:
    chunk = AudioChunk(data=b"\x00" * 10, sample_rate=16000, sample_width=1)
    with pytest.raises(SpeechError):
        apply_gain(chunk, 0.5)


def test_apply_gain_preserves_format_and_timestamp() -> None:
    chunk = make_chunk(0.05, sample_rate=22050)
    result = apply_gain(chunk, 1.5)
    assert result.sample_rate == chunk.sample_rate
    assert result.channels == chunk.channels
    assert result.sample_width == chunk.sample_width
    assert result.timestamp == chunk.timestamp
