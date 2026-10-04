"""``_format_schedule_label`` renders every schedule kind without raising.

A weekly job scheduled correctly, because ``domain/cron/next_run.py`` reads
``schedule.weekday``, and then crashed when the worker rendered its task card,
because the label formatter read ``s.day_of_week``. ``WeeklySchedule`` is
``extra="forbid"``, so the attribute does not exist and the read raised
``AttributeError`` inside ``execute_job``, which the caller swallows and reports
as ``completed``.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from lca.contracts.models.cron.models import (
    AgentExecution,
    ChatDelivery,
    CronJob,
    DailySchedule,
    HourlySchedule,
    IntervalSchedule,
    OneShotSchedule,
    WeeklySchedule,
)
from lca.infrastructure.cron.worker_runner import _format_schedule_label


def _job(schedule: object) -> CronJob:
    return CronJob(
        id="j1",
        title="t",
        schedule=schedule,
        timezone="Asia/Shanghai",
        body="b",
        execution=AgentExecution(kind="agent"),
        delivery_targets=(ChatDelivery(chat_id="tpc_test"),),
        owner="asst_test",
        created_chat_id="tpc_test",
        anchor_at=datetime(2026, 10, 4, 6, 0, tzinfo=UTC),
    )


def test_weekly_label_reads_the_weekday_field() -> None:
    label = _format_schedule_label(
        _job(WeeklySchedule(kind="weekly", weekday=2, hour=9, minute=5)),
    )
    assert label == "每周三 09:05"


@pytest.mark.parametrize("weekday", range(7))
def test_weekly_label_covers_every_day(weekday: int) -> None:
    label = _format_schedule_label(
        _job(WeeklySchedule(kind="weekly", weekday=weekday, hour=0, minute=0)),
    )
    assert label.startswith("每")
    assert "00:00" in label


def test_oneshot_label() -> None:
    at = datetime(2026, 10, 4, 14, 33, tzinfo=UTC)
    assert _format_schedule_label(_job(OneShotSchedule(kind="oneshot", at=at))) == (
        "一次性 2026-10-04 14:33"
    )


@pytest.mark.parametrize(
    ("every_seconds", "expected"),
    [
        (30, "每 30 秒"),
        (90, "每 90 秒"),
        (600, "每 10 分钟"),
        (7200, "每 2 小时"),
    ],
)
def test_interval_label(every_seconds: int, expected: str) -> None:
    schedule = IntervalSchedule(kind="interval", every_seconds=every_seconds)
    assert _format_schedule_label(_job(schedule)) == expected


def test_hourly_and_daily_labels() -> None:
    assert (
        _format_schedule_label(
            _job(HourlySchedule(kind="hourly", minute=7)),
        )
        == "每小时第 07 分"
    )
    assert (
        _format_schedule_label(
            _job(DailySchedule(kind="daily", hour=22, minute=30)),
        )
        == "每天 22:30"
    )
