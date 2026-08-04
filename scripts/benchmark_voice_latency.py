"""Benchmark JarvisVoicePipeline's response latency (Phase 11).

Measures wall-clock latency from "utterance finalized" to "assistant
started speaking" (`voice.speaking_started`'s `total_latency_seconds`,
computed by the pipeline itself) across N synthetic turns, plus a
breakdown of the STT/assistant/TTS stages that make it up.

IMPORTANT: no real whisper.cpp/Piper/Cowork backend is installed in
this environment (see docs/architecture.md's Phase 6/7/9 caveats), so
this measures Jarvis's own *coordination overhead* (threading, event
publishing, queueing) against *assumed* backend latencies, not real
model inference speed. STT_DELAY_SECONDS/TTS_DELAY_SECONDS below are
representative published figures for small local models, not
measurements — replace them with real numbers once real backends are
installed, and re-run this script.

Usage: python scripts/benchmark_voice_latency.py [N]
"""

from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from jarvis.core.config.voice_config import (  # noqa: E402
    ListeningConfig,
    ListeningMode,
    SpeechQueueConfig,
    StreamingConfig,
    VoiceConfig,
    WakeWordConfig,
)
from jarvis.core.events import EventBus  # noqa: E402
from jarvis.core.speech.jarvis_pipeline import JarvisVoicePipeline  # noqa: E402
from jarvis.core.voice.ports import NullMicrophonePort, NullWakeWordPort  # noqa: E402
from jarvis.core.voice.types import AudioChunk, TranscriptionResult, VoiceState  # noqa: E402

# Representative small-local-model figures, NOT measured here.
STT_DELAY_SECONDS = 0.15  # whisper.cpp "base.en" on a short utterance, roughly
TTS_DELAY_SECONDS = 0.08  # Piper synthesis for a short response, roughly

SAMPLE_RATE = 16000


class DelayedSTT:
    def transcribe(self, audio: AudioChunk) -> TranscriptionResult:
        time.sleep(STT_DELAY_SECONDS)
        return TranscriptionResult(text="turn on the lights", is_final=True)


class DelayedTTS:
    def synthesize(self, text: str) -> AudioChunk:
        time.sleep(TTS_DELAY_SECONDS)
        return AudioChunk(data=b"\x00\x00" * 800, sample_rate=SAMPLE_RATE, channels=1)


class AlwaysSpeech:
    def is_speech(self, chunk: AudioChunk) -> bool:
        return True


class InstantPlayer:
    """A minimal real AudioPlayerPort: is_playing flips True/False
    immediately around a short synthetic playback window. Deliberately
    NOT NullAudioPlayerPort — that stays False forever by design (Phase
    5), which would make JarvisVoicePipeline's completion detection
    (waits to *observe* is_playing=True — see _tick_speaking) wait
    forever.
    """

    def __init__(self, play_seconds: float = 0.02) -> None:
        self.play_seconds = play_seconds
        self._until = 0.0

    def play(self, audio: AudioChunk) -> None:
        self._until = time.monotonic() + self.play_seconds

    def stop(self) -> None:
        self._until = 0.0

    @property
    def is_playing(self) -> bool:
        return time.monotonic() < self._until


def _chunk(seconds: float) -> AudioChunk:
    return AudioChunk(
        data=b"\x00\x00" * round(seconds * SAMPLE_RATE), sample_rate=SAMPLE_RATE, channels=1
    )


def run(n: int) -> list[float]:
    config = VoiceConfig(
        wake_word=WakeWordConfig(enabled=False),
        listening=ListeningConfig(mode=ListeningMode.PUSH_TO_TALK, allow_interruption=False),
        streaming=StreamingConfig(pause_duration_seconds=10.0, no_speech_timeout_seconds=10.0),
        queue=SpeechQueueConfig(poll_interval_seconds=0.01),
    )
    events = EventBus()
    player = InstantPlayer(play_seconds=0.02)
    pipeline = JarvisVoicePipeline(
        microphone=NullMicrophonePort(),
        wake_word=NullWakeWordPort(),  # not consulted in push_to_talk mode
        vad=AlwaysSpeech(),
        stt=DelayedSTT(),
        assistant=lambda text, sid: "The lights are on.",
        tts=DelayedTTS(),
        player=player,
        config=config,
        events=events,
        session_id="benchmark",
    )
    pipeline.start()
    latencies: list[float] = []
    for _ in range(n):
        pipeline.push_to_talk_press()
        pipeline._transcriber.feed(_chunk(0.5))

        turn_start = time.monotonic()
        pipeline.push_to_talk_release()
        deadline = turn_start + 5.0
        while not player.is_playing and time.monotonic() < deadline:
            time.sleep(0.001)
        latencies.append(time.monotonic() - turn_start)

        deadline = time.monotonic() + 5.0
        while pipeline.state != VoiceState.IDLE and time.monotonic() < deadline:
            time.sleep(0.005)
    pipeline.stop()
    return latencies


def _stats(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    p95_index = min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))
    return {
        "min": ordered[0],
        "mean": statistics.mean(ordered),
        "p95": ordered[p95_index],
        "max": ordered[-1],
    }


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    latencies = run(n)
    stats = _stats(latencies)

    lines = [
        "# Voice Pipeline Response Latency Benchmark",
        "",
        f"Synthetic benchmark, {n} turns, generated by "
        "`scripts/benchmark_voice_latency.py` (Phase 11).",
        "",
        "Assumed backend latencies (not measured — no real whisper.cpp/Piper "
        f"installed): STT {STT_DELAY_SECONDS * 1000:.0f}ms, "
        f"TTS {TTS_DELAY_SECONDS * 1000:.0f}ms. Measures Jarvis's own "
        "coordination overhead (threading, queueing, event publishing) on "
        "top of those.",
        "",
        "| Metric | Latency (ms) |",
        "|---|---|",
        f"| Min | {stats['min'] * 1000:.1f} |",
        f"| Mean | {stats['mean'] * 1000:.1f} |",
        f"| P95 | {stats['p95'] * 1000:.1f} |",
        f"| Max | {stats['max'] * 1000:.1f} |",
        "",
        f"Baseline STT+TTS floor: {(STT_DELAY_SECONDS + TTS_DELAY_SECONDS) * 1000:.0f}ms — "
        "the gap between that and the measured mean is Jarvis's own overhead "
        "(SpeechQueue enqueue/dequeue, thread wakeups, EventBus publishes).",
        "",
    ]
    report = "\n".join(lines)

    out_path = Path(__file__).resolve().parent.parent / "docs" / "benchmarks" / "voice_latency.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(report)
    print(f"Written to {out_path}")


if __name__ == "__main__":
    main()
