"""Abstract interfaces (ports) the orchestrator depends on.

This is the dependency-inversion boundary of the whole package: the
orchestrator is written entirely against these `Protocol`s, never
against a concrete class. A later phase adding a SQLite/FAISS-backed
memory plugin, or a PyAutoGUI/Playwright-backed automation plugin,
only needs to implement these shapes and register an instance in the
ServiceContainer under the port's type — no orchestrator code changes.

`Protocol` (structural typing) is used instead of an ABC base class
deliberately: a concrete implementation doesn't need to import this
module or subclass anything to satisfy the contract, which keeps the
dependency arrow pointing one way (implementations depend on nothing;
the orchestrator depends on the shape).

Two default implementations are included here — NullMemoryPort and
NullAutomationPort — following the Null Object pattern. They are not
placeholders for unfinished work: recall/remember/execute are fully
implemented and safe to run in production, and they are the permanent
answer to "what happens when no memory or automation backend is
configured yet." Registering them by default means the orchestrator's
request-handling code never needs an `if backend is None` branch.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from jarvis.orchestrator.models import Intent, Session, Turn

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MemoryItem:
    """A single fact/exchange returned by MemoryPort.recall()."""

    content: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AutomationAction:
    """A single automation request (e.g. "click", "open_browser", "type_text")."""

    name: str
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AutomationResult:
    """The outcome of running an AutomationAction."""

    success: bool
    output: Any = None
    error: str | None = None


@runtime_checkable
class MemoryPort(Protocol):
    """Long-term memory, spanning process restarts. Implemented in a later
    phase by a SQLite/FAISS-backed plugin; until then, NullMemoryPort.
    """

    def recall(self, session_id: str, query: str, *, limit: int = 5) -> list[MemoryItem]:
        """Return up to `limit` memory items relevant to `query`."""
        ...

    def remember(self, session_id: str, turn: Turn) -> None:
        """Persist a completed conversation turn for future recall."""
        ...


@runtime_checkable
class AutomationPort(Protocol):
    """Desktop/browser automation, e.g. PyAutoGUI or Playwright, added in a
    later phase. Until then, NullAutomationPort.
    """

    def execute(self, action: AutomationAction) -> AutomationResult:
        """Run a single automation action and report the outcome."""
        ...


@runtime_checkable
class IntentRecognizer(Protocol):
    """Turns raw request text into an Intent.

    The default implementation (PatternIntentRecognizer) matches
    against patterns plugins registered via CapabilityRegistry. This
    is a separate port — rather than baking pattern matching into the
    orchestrator — specifically so a future phase can swap in an
    LLM-backed recognizer without touching Orchestrator.handle().
    """

    def recognize(self, text: str, session: Session) -> Intent:
        ...


class NullMemoryPort:
    """Default MemoryPort: no long-term memory backend configured.

    recall() always returns an empty list; remember() discards the
    turn. Both are logged at DEBUG so the absence of a real backend is
    visible without being noisy.
    """

    def recall(self, session_id: str, query: str, *, limit: int = 5) -> list[MemoryItem]:
        logger.debug(
            "NullMemoryPort.recall(session_id=%r, query=%r) — no memory backend configured",
            session_id,
            query,
        )
        return []

    def remember(self, session_id: str, turn: Turn) -> None:
        logger.debug(
            "NullMemoryPort.remember(session_id=%r) — no memory backend configured, discarding",
            session_id,
        )


class NullAutomationPort:
    """Default AutomationPort: no automation backend configured.

    Unlike NullMemoryPort, silently discarding is misleading here — a
    plugin that requests automation genuinely cannot proceed, so this
    logs at WARNING and reports failure explicitly via
    AutomationResult.success=False rather than raising, so a capability
    handler can degrade gracefully (e.g. fall back to a text answer).
    """

    def execute(self, action: AutomationAction) -> AutomationResult:
        logger.warning(
            "NullAutomationPort.execute(action=%r) — no automation backend configured", action.name
        )
        return AutomationResult(
            success=False, output=None, error="No automation backend is configured"
        )
