"""A small, dependency-free 5-field cron matcher — "implement scheduled
workflows" needs recurring schedules like "daily at 02:00" or "every
Monday at 09:00", and this project prefers a self-contained
implementation over a new hard dependency when the common subset is
easy to cover correctly (same reasoning as `core/version_utils.py`'s
dotted-version comparison and `core/planning/dependencies.py`'s
heuristics).

Supports standard 5-field cron (`minute hour day month weekday`), each
field accepting `*`, comma lists (`1,2,3`), ranges (`1-5`), and step
values (`*/15`, `1-10/2`). `weekday` follows the standard cron
convention: 0=Sunday .. 6=Saturday.

One deliberate simplification from real cron: when both `day` and
`weekday` are restricted (not `*`), this implementation requires BOTH
to match (AND), not either (OR, real cron's well-known behavior). For
the maintenance-style schedules this phase targets ("daily", "weekly on
a given day", "monthly on a given day-of-month"), AND semantics are
the intuitive reading and avoid a well-documented cron gotcha; a
workflow needing real OR semantics can express it as two separate
scheduled workflows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from jarvis.core.exceptions import InvalidCronExpressionError

_FIELD_BOUNDS = {
    "minute": (0, 59),
    "hour": (0, 23),
    "day": (1, 31),
    "month": (1, 12),
    "weekday": (0, 6),
}

# How far into the future to search for a matching time before giving
# up — an expression like "0 0 31 2 *" (Feb 31st) never matches, and
# this bounds that search instead of looping forever.
_SEARCH_HORIZON_DAYS = 4 * 366


def _parse_field(expr: str, lo: int, hi: int) -> frozenset[int]:
    values: set[int] = set()
    for part in expr.split(","):
        step = 1
        if "/" in part:
            part, step_str = part.split("/", 1)
            step = int(step_str)
        if part == "*":
            start, end = lo, hi
        elif "-" in part:
            start_str, end_str = part.split("-", 1)
            start, end = int(start_str), int(end_str)
        else:
            start = end = int(part)
        values.update(v for v in range(start, end + 1) if (v - lo) % step == 0)
    if not values:
        raise InvalidCronExpressionError(f"cron field {expr!r} matches nothing")
    return frozenset(values)


@dataclass(frozen=True)
class CronSchedule:
    minute: frozenset[int]
    hour: frozenset[int]
    day: frozenset[int]
    month: frozenset[int]
    weekday: frozenset[int]

    @classmethod
    def parse(cls, expr: str) -> CronSchedule:
        fields = expr.split()
        if len(fields) != 5:
            raise InvalidCronExpressionError(
                f"cron expression {expr!r} must have exactly 5 fields "
                f"(minute hour day month weekday), got {len(fields)}"
            )
        minute, hour, day, month, weekday = fields
        try:
            return cls(
                minute=_parse_field(minute, *_FIELD_BOUNDS["minute"]),
                hour=_parse_field(hour, *_FIELD_BOUNDS["hour"]),
                day=_parse_field(day, *_FIELD_BOUNDS["day"]),
                month=_parse_field(month, *_FIELD_BOUNDS["month"]),
                weekday=_parse_field(weekday, *_FIELD_BOUNDS["weekday"]),
            )
        except ValueError as exc:
            raise InvalidCronExpressionError(f"invalid cron expression {expr!r}: {exc}") from exc

    def matches(self, dt: datetime) -> bool:
        cron_weekday = (dt.weekday() + 1) % 7  # Python: Mon=0..Sun=6 -> cron: Sun=0..Sat=6
        return (
            dt.minute in self.minute
            and dt.hour in self.hour
            and dt.day in self.day
            and dt.month in self.month
            and cron_weekday in self.weekday
        )


def _next_month_start(dt: datetime) -> datetime:
    year = dt.year + (dt.month // 12)
    month = dt.month % 12 + 1
    return dt.replace(year=year, month=month, day=1, hour=0, minute=0, second=0, microsecond=0)


def next_run_after(expr: str, after: datetime) -> datetime:
    """The next datetime matching `expr` strictly after `after`, minute
    granularity (seconds/microseconds are truncated). Advances by
    whichever field currently mismatches — month/day/hour/minute — so
    this stays fast even when the answer is months away, rather than
    stepping minute-by-minute.
    """
    schedule = CronSchedule.parse(expr)
    candidate = (after + timedelta(minutes=1)).replace(second=0, microsecond=0)
    horizon = candidate + timedelta(days=_SEARCH_HORIZON_DAYS)

    while candidate <= horizon:
        if candidate.month not in schedule.month:
            candidate = _next_month_start(candidate)
            continue
        cron_weekday = (candidate.weekday() + 1) % 7
        if candidate.day not in schedule.day or cron_weekday not in schedule.weekday:
            candidate = (candidate + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            continue
        if candidate.hour not in schedule.hour:
            candidate = (candidate + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
            continue
        if candidate.minute not in schedule.minute:
            candidate = candidate + timedelta(minutes=1)
            continue
        return candidate

    raise InvalidCronExpressionError(
        f"no matching run time found for cron {expr!r} within {_SEARCH_HORIZON_DAYS} days"
    )
