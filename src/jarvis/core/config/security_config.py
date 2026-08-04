"""security.yaml — the Jarvis Security Manager's settings (Phase 19):
per-level rate limits, which levels require confirmation, and where
its audit log/session history live.

No `enabled` flag: SecurityManager is pure local logic (no external
backend), always constructed and always wired in front of
`ExecutionEngine` — the same "always real, no Null default" choice
Phase 17's `PlanningEngine` made, and the one that makes "Claude Cowork
must never bypass the security layer" true structurally rather than
by convention.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

SECURITY_FILENAME = "security.yaml"


class RateLimitConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    read_per_minute: int = Field(120, gt=0)
    write_per_minute: int = Field(60, gt=0)
    execute_per_minute: int = Field(30, gt=0)
    dangerous_per_minute: int = Field(5, gt=0)
    administrator_per_minute: int = Field(5, gt=0)


class SecurityConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    audit_log_path: Path = Path("logs/security_audit.jsonl")
    rate_limits: RateLimitConfig = Field(default_factory=RateLimitConfig)

    # Which permission levels require a confirmation before running,
    # beyond the always-required implicit confirmation BLOCKED already
    # gets by being denied outright.
    confirmation_required_levels: list[str] = Field(
        default_factory=lambda: ["dangerous", "administrator"]
    )

    # How many past security decisions to keep per requester in
    # SessionHistory before the oldest are dropped.
    session_history_limit: int = Field(200, gt=0)
