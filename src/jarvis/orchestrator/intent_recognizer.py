"""Default IntentRecognizer implementation.

Deliberately not an LLM call: Phase 2 is about the orchestrator's
shape, not natural-language understanding quality. Matching request
text against patterns that plugins themselves registered means intent
recognition and capability routing share one source of truth (the
CapabilityRegistry) — there is no separate "list of intents" for the
two to drift out of sync on.

Because this implements the `IntentRecognizer` Protocol structurally
(see ports.py), a later phase can introduce an LLM-backed recognizer
as a drop-in replacement — register it under the same `IntentRecognizer`
key in the ServiceContainer — without changing Orchestrator at all.
"""

from __future__ import annotations

import logging

from jarvis.orchestrator.capability_registry import CapabilityRegistry
from jarvis.orchestrator.models import Intent, Session

logger = logging.getLogger(__name__)

UNKNOWN_INTENT = "unknown"


class PatternIntentRecognizer:
    def __init__(self, registry: CapabilityRegistry) -> None:
        self._registry = registry

    def recognize(self, text: str, session: Session) -> Intent:
        result = self._registry.match(text)
        if result is None:
            logger.debug(
                "No capability pattern matched text=%r (session=%s)", text, session.session_id
            )
            return Intent(name=UNKNOWN_INTENT, confidence=0.0, raw_text=text)

        return Intent(
            name=result.registration.name,
            confidence=1.0,
            raw_text=text,
            matched_pattern=result.match.re.pattern,
        )
