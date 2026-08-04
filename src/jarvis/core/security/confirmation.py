"""ConfirmationPort: "implement confirmation dialogs" — the interface
for asking a human to approve a DANGEROUS/ADMINISTRATOR-level action
before it runs, plus two real, working implementations. No GUI/voice
dialog is built here (that belongs to whatever surface actually talks
to the user — the API, a future desktop UI, the voice pipeline); this
phase's job is the seam SecurityManager calls through and a usable
default, the same "design the interface, ship a real minimal
implementation" scope every prior phase's confirmation-adjacent work
used (Phase 4's `confirmed=True` flag, Phase 5's voice pipeline
interfaces).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class ConfirmationPort(Protocol):
    def confirm(self, prompt: str) -> bool: ...


class AutoDenyConfirmation:
    """No confirmation surface wired up. Fails closed: a
    DANGEROUS/ADMINISTRATOR action with nobody able to approve it is
    denied, not silently allowed — the same "safe default" every Null
    Object in this project follows, just phrased as a real decision
    rather than an unavailable-backend error, since "nobody answered"
    is a legitimate outcome here, not a misconfiguration.
    """

    def confirm(self, prompt: str) -> bool:
        logger.warning(
            "AutoDenyConfirmation: denying (no confirmation surface configured): %s", prompt
        )
        return False


class CallbackConfirmation:
    """Implements ConfirmationPort by delegating to any synchronous
    callable — a CLI prompt, a future desktop dialog, a voice
    yes/no exchange. Real and usable today without this phase needing
    to build any particular UI.
    """

    def __init__(self, callback: Callable[[str], bool]) -> None:
        self._callback = callback

    def confirm(self, prompt: str) -> bool:
        return bool(self._callback(prompt))
