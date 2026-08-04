from __future__ import annotations

from jarvis.orchestrator.capability_registry import CapabilityRegistry
from jarvis.orchestrator.intent_recognizer import UNKNOWN_INTENT, PatternIntentRecognizer
from jarvis.orchestrator.models import CapabilityContext, CapabilityResult, Session


def _noop_handler(context: CapabilityContext) -> CapabilityResult:
    return CapabilityResult()


def test_recognizes_registered_pattern(
    capability_registry: CapabilityRegistry, intent_recognizer: PatternIntentRecognizer
) -> None:
    capability_registry.register("greet", _noop_handler, patterns=[r"\bhello\b"], plugin="greeter")
    intent = intent_recognizer.recognize("hello there", Session(session_id="s1"))
    assert intent.name == "greet"
    assert intent.confidence == 1.0


def test_returns_unknown_for_unmatched_text(intent_recognizer: PatternIntentRecognizer) -> None:
    intent = intent_recognizer.recognize("gibberish nonsense", Session(session_id="s1"))
    assert intent.name == UNKNOWN_INTENT
    assert intent.confidence == 0.0
