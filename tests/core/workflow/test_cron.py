from __future__ import annotations

from datetime import UTC, datetime

import pytest

from jarvis.core.exceptions import InvalidCronExpressionError
from jarvis.core.workflow.cron import CronSchedule, next_run_after


def test_daily_at_time() -> None:
    after = datetime(2026, 8, 4, 10, 0, tzinfo=UTC)
    assert next_run_after("0 2 * * *", after) == datetime(2026, 8, 5, 2, 0, tzinfo=UTC)


def test_daily_at_time_already_past_today_rolls_to_tomorrow() -> None:
    after = datetime(2026, 8, 4, 1, 0, tzinfo=UTC)
    assert next_run_after("0 2 * * *", after) == datetime(2026, 8, 4, 2, 0, tzinfo=UTC)


def test_every_15_minutes() -> None:
    after = datetime(2026, 8, 4, 10, 3, tzinfo=UTC)
    assert next_run_after("*/15 * * * *", after) == datetime(2026, 8, 4, 10, 15, tzinfo=UTC)


def test_weekly_on_monday() -> None:
    # 2026-08-04 is a Tuesday; next Monday 09:00 is 2026-08-10.
    after = datetime(2026, 8, 4, 10, 0, tzinfo=UTC)
    assert next_run_after("0 9 * * 1", after) == datetime(2026, 8, 10, 9, 0, tzinfo=UTC)


def test_monthly_on_day() -> None:
    after = datetime(2026, 8, 4, 10, 0, tzinfo=UTC)
    assert next_run_after("0 0 15 * *", after) == datetime(2026, 8, 15, 0, 0, tzinfo=UTC)


def test_wrong_field_count_raises() -> None:
    with pytest.raises(InvalidCronExpressionError):
        CronSchedule.parse("0 2 * *")


def test_unparseable_field_raises() -> None:
    with pytest.raises(InvalidCronExpressionError):
        CronSchedule.parse("not-a-number * * * *")


def test_impossible_expression_raises_within_search_horizon() -> None:
    after = datetime(2026, 8, 4, 10, 0, tzinfo=UTC)
    with pytest.raises(InvalidCronExpressionError):
        next_run_after("0 0 31 2 *", after)  # Feb 31st never exists


def test_range_and_list_fields() -> None:
    schedule = CronSchedule.parse("0 9-11 * * 1,3,5")
    assert schedule.hour == frozenset({9, 10, 11})
    assert schedule.weekday == frozenset({1, 3, 5})
