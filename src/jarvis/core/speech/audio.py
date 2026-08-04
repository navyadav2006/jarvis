"""Small, dependency-light audio helpers shared by the speech module.

Everything here assumes 16-bit PCM (`AudioChunk.sample_width == 2`) —
whisper.cpp's and webrtcvad's native expectation. A real
MicrophonePort implementation is responsible for producing audio in
this format; nothing here resamples or converts sample width/rate.

`chunk_duration_seconds`, `concat_chunks`, and `apply_gain` need
nothing beyond the standard library — they're what let
StreamingTranscriber and SpeechQueue be fully testable with zero
optional dependencies installed. Only `pcm16_bytes_to_float32` needs
numpy (lazily imported), since it's whisper.cpp-specific input
preparation.
"""

from __future__ import annotations

import array

from jarvis.core.exceptions import SpeechBackendUnavailableError, SpeechError
from jarvis.core.voice.types import AudioChunk

_INT16_MIN = -32768
_INT16_MAX = 32767


def chunk_duration_seconds(chunk: AudioChunk) -> float:
    """How many seconds of audio `chunk` represents."""
    if chunk.sample_width != 2:
        raise SpeechError(
            f"expected 16-bit PCM (sample_width=2), got sample_width={chunk.sample_width}"
        )
    num_samples = len(chunk.data) / chunk.sample_width / chunk.channels
    return num_samples / chunk.sample_rate


def concat_chunks(chunks: list[AudioChunk]) -> AudioChunk:
    """Concatenate same-format chunks into one, preserving the first
    chunk's format and timestamp (the utterance's start time).
    """
    if not chunks:
        raise SpeechError("cannot concatenate an empty list of chunks")
    first = chunks[0]
    for other in chunks[1:]:
        if (other.sample_rate, other.channels, other.sample_width) != (
            first.sample_rate,
            first.channels,
            first.sample_width,
        ):
            raise SpeechError("cannot concatenate audio chunks with different formats")
    return AudioChunk(
        data=b"".join(chunk.data for chunk in chunks),
        sample_rate=first.sample_rate,
        channels=first.channels,
        sample_width=first.sample_width,
        timestamp=first.timestamp,
    )


def apply_gain(chunk: AudioChunk, gain: float) -> AudioChunk:
    """Scale 16-bit PCM samples by `gain` (1.0 = unchanged, 0.0 = silence,
    >1.0 = amplified), used by SpeechQueue for volume control.

    Implemented with the standard library `array` module rather than
    numpy specifically so SpeechQueue's volume handling has no required
    dependency, matching StreamingTranscriber's "core buffering logic
    needs nothing beyond core/voice/'s plain types" property. Samples
    are clamped to the valid int16 range — without clamping, a gain
    that pushes a sample past +-32767 would wrap around to a
    near-opposite value instead of clipping, producing loud, sharp
    distortion rather than the harsh-but-expected sound of clipping.
    """
    if gain < 0:
        raise SpeechError(f"gain must be >= 0, got {gain}")
    if chunk.sample_width != 2:
        raise SpeechError(
            "apply_gain requires 16-bit PCM (sample_width=2), "
            f"got sample_width={chunk.sample_width}"
        )
    if gain == 1.0 or not chunk.data:
        return chunk

    samples = array.array("h")
    samples.frombytes(chunk.data)
    scaled = array.array(
        "h", (_clamp_int16(round(sample * gain)) for sample in samples)
    )
    return AudioChunk(
        data=scaled.tobytes(),
        sample_rate=chunk.sample_rate,
        channels=chunk.channels,
        sample_width=chunk.sample_width,
        timestamp=chunk.timestamp,
    )


def _clamp_int16(value: int) -> int:
    return max(_INT16_MIN, min(_INT16_MAX, value))


def pcm16_bytes_to_float32(data: bytes):
    """Convert 16-bit PCM bytes to a float32 numpy array normalized to
    [-1, 1] — the input format whisper.cpp/pywhispercpp expects.
    """
    try:
        import numpy as np
    except ImportError as exc:
        raise SpeechBackendUnavailableError(
            "numpy is not installed; install the 'voice' extra "
            "(pip install -e '.[voice]') to use the speech module"
        ) from exc

    if not data:
        return np.zeros(0, dtype=np.float32)
    samples = np.frombuffer(data, dtype=np.int16)
    return samples.astype(np.float32) / 32768.0
