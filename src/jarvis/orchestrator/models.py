"""Domain types passed between the orchestrator, capability handlers, and ports.

Kept dependency-free of any concrete plugin/memory/automation
implementation — everything here is a plain data type. `CapabilityContext`
is the only place that references the port *interfaces* (MemoryPort,
AutomationPort), and only under `TYPE_CHECKING`, so this module never
has a runtime import cycle with ports.py even though ports.py imports
from here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from jarvis.core.filesystem import FilesystemPort
    from jarvis.orchestrator.ports import AutomationPort, MemoryItem, MemoryPort


@dataclass(frozen=True)
class Request:
    """A single inbound request, regardless of where it came from.

    `source` distinguishes the channel (api/voice/cli/...) without the
    orchestrator needing to special-case any of them — capability
    handlers can inspect it if a response should differ by channel
    (e.g. don't speak a long answer that came in over voice).
    """

    text: str
    session_id: str
    source: str = "api"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Intent:
    """What the orchestrator believes the request means.

    `name` of "unknown" is a sentinel, not an error: it means no
    registered capability's patterns matched, and the orchestrator
    responds accordingly (see Orchestrator.handle).
    """

    name: str
    confidence: float
    raw_text: str
    matched_pattern: str | None = None


@dataclass
class Turn:
    """One request/response exchange, as recorded in session history
    and handed to MemoryPort.remember() for optional long-term storage.
    """

    request_text: str
    response_text: str
    intent_name: str
    timestamp: datetime


@dataclass
class Session:
    """Short-lived, in-process conversation state for one session_id.

    This is deliberately NOT the same thing as long-term memory
    (MemoryPort): a Session evaporates when the process restarts and
    exists purely so a multi-turn conversation can refer to what was
    just said. Long-term recall across restarts is MemoryPort's job.
    """

    session_id: str
    history: list[Turn] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    max_history: int = 50

    def add_turn(self, turn: Turn) -> None:
        self.history.append(turn)
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history :]


@dataclass
class CapabilityResult:
    """What a capability handler returns to the orchestrator.

    `state_updates` is merged into the session's context dict after a
    successful call — this is how a handler contributes to multi-turn
    state (e.g. slot-filling) without being given a mutable reference
    to the Session itself, which would let it clobber history or other
    plugins' context keys.
    """

    text: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    state_updates: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CapabilityContext:
    """Everything a capability handler is given to do its job.

    This is the single seam through which a plugin ever touches
    memory, automation, or the filesystem: it receives the abstract
    MemoryPort / AutomationPort / FilesystemPort here, injected by the
    orchestrator, and never imports or constructs a concrete
    implementation itself. That keeps plugins as ignorant of "how
    memory/automation/the filesystem actually work" as the orchestrator
    is of "how any given plugin works."
    """

    request: Request
    intent: Intent
    session: Session
    memory: MemoryPort
    automation: AutomationPort
    filesystem: FilesystemPort
    recalled: list[MemoryItem]


@dataclass(frozen=True)
class Response:
    """What the orchestrator returns to whatever called it (API, CLI, voice loop)."""

    session_id: str
    intent_name: str
    handled: bool
    text: str | None
    data: dict[str, Any] = field(default_factory=dict)
