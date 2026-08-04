from __future__ import annotations

from jarvis.core.security.rate_limiter import RateLimiter
from jarvis.core.security.types import PermissionLevel


def test_allows_up_to_the_configured_limit() -> None:
    limiter = RateLimiter({PermissionLevel.READ: 3})
    assert limiter.allow("cowork", PermissionLevel.READ) is True
    assert limiter.allow("cowork", PermissionLevel.READ) is True
    assert limiter.allow("cowork", PermissionLevel.READ) is True
    assert limiter.allow("cowork", PermissionLevel.READ) is False


def test_unconfigured_level_is_never_limited() -> None:
    limiter = RateLimiter({PermissionLevel.READ: 1})
    for _ in range(10):
        assert limiter.allow("cowork", PermissionLevel.WRITE) is True


def test_keys_are_isolated_per_requester() -> None:
    limiter = RateLimiter({PermissionLevel.READ: 1})
    assert limiter.allow("cowork", PermissionLevel.READ) is True
    assert limiter.allow("other-plugin", PermissionLevel.READ) is True


def test_keys_are_isolated_per_level() -> None:
    limiter = RateLimiter({PermissionLevel.READ: 1, PermissionLevel.WRITE: 1})
    assert limiter.allow("cowork", PermissionLevel.READ) is True
    assert limiter.allow("cowork", PermissionLevel.WRITE) is True


def test_remaining_counts_down_and_floors_at_zero() -> None:
    limiter = RateLimiter({PermissionLevel.READ: 2})
    assert limiter.remaining("cowork", PermissionLevel.READ) == 2
    limiter.allow("cowork", PermissionLevel.READ)
    assert limiter.remaining("cowork", PermissionLevel.READ) == 1
    limiter.allow("cowork", PermissionLevel.READ)
    limiter.allow("cowork", PermissionLevel.READ)
    assert limiter.remaining("cowork", PermissionLevel.READ) == 0


def test_remaining_for_unconfigured_level_is_none() -> None:
    limiter = RateLimiter({PermissionLevel.READ: 2})
    assert limiter.remaining("cowork", PermissionLevel.WRITE) is None


def test_denied_attempts_still_count_against_the_window() -> None:
    limiter = RateLimiter({PermissionLevel.READ: 1})
    limiter.allow("cowork", PermissionLevel.READ)
    assert limiter.allow("cowork", PermissionLevel.READ) is False
    assert limiter.allow("cowork", PermissionLevel.READ) is False
