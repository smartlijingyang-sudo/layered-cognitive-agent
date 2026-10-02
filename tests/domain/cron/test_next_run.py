"""``next_run`` pure-function tests (ADR-0268 §5).

覆盖：一次性、间隔、小时/日/周、DST 缺口与歧义、类型化拒绝、
纯函数确定性（同一输入两次结果相同）。
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

import pytest

from lca.contracts.models.cron.models import (
    AgentExecution,
    ChatDelivery,
    CronJob,
    CronValidationError,
    DailySchedule,
    HourlySchedule,
    IntervalSchedule,
    OneShotSchedule,
    WeeklySchedule,
)
from lca.domain.cron.next_run import next_run

UTC = UTC
NY = "America/New_York"


def _job(schedule: object, *, timezone: str = "UTC") -> CronJob:
    return CronJob(
        id="job_1",
        title="提醒",
        schedule=schedule,  # type: ignore[arg-type]
        timezone=timezone,
        body="b",
        execution=AgentExecution(),
        delivery_targets=(ChatDelivery(chat_id="chat_1"),),
        owner="user_1",
        created_chat_id="chat_1",
        anchor_at=datetime(2026, 10, 2, 9, 0, tzinfo=UTC),
    )


def test_oneshot_future_upcoming() -> None:
    at = datetime(2026, 10, 3, 9, 0, tzinfo=UTC)
    job = _job(OneShotSchedule(at=at))
    fire = next_run(job, last_run=None, now=datetime(2026, 10, 2, 9, 0, tzinfo=UTC))
    assert fire.upcoming == at
    assert fire.due is False


def test_oneshot_past_is_due() -> None:
    at = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
    job = _job(OneShotSchedule(at=at))
    fire = next_run(job, last_run=None, now=datetime(2026, 10, 2, 9, 0, tzinfo=UTC))
    assert fire.upcoming is None
    assert fire.due is True


def test_oneshot_with_last_run_not_upcoming() -> None:
    at = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
    job = _job(OneShotSchedule(at=at))
    fire = next_run(job, last_run=at, now=datetime(2026, 10, 2, 9, 0, tzinfo=UTC))
    assert fire.upcoming is None
    assert fire.due is False


def test_interval_first_candidate_after_anchor() -> None:
    anchor = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)
    job = _job(IntervalSchedule(every_seconds=60), timezone="UTC")
    job = job.model_copy(update={"anchor_at": anchor})
    fire = next_run(job, last_run=None, now=anchor)
    assert fire.upcoming == anchor + timedelta(seconds=60)
    assert fire.due is False


def test_interval_candidate_equal_now_is_due() -> None:
    anchor = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)
    job = _job(IntervalSchedule(every_seconds=60), timezone="UTC")
    job = job.model_copy(update={"anchor_at": anchor})
    last_run = anchor
    now = anchor + timedelta(seconds=60)  # 当前正好是下一候选档
    fire = next_run(job, last_run=last_run, now=now)
    assert fire.due is True
    assert fire.upcoming == now + timedelta(seconds=60)


def test_interval_advances_past_now() -> None:
    anchor = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)
    job = _job(IntervalSchedule(every_seconds=60), timezone="UTC")
    job = job.model_copy(update={"anchor_at": anchor})
    now = anchor + timedelta(seconds=125)  # 已经越过第一档 60s，第二档 120s 也过了
    fire = next_run(job, last_run=None, now=now)
    assert fire.upcoming == anchor + timedelta(seconds=180)
    assert fire.due is False


def test_hourly_next_boundary() -> None:
    job = _job(HourlySchedule(minute=30), timezone="UTC")
    now = datetime(2026, 10, 2, 9, 10, tzinfo=UTC)
    fire = next_run(job, last_run=None, now=now)
    assert fire.upcoming == datetime(2026, 10, 2, 9, 30, tzinfo=UTC)
    assert fire.due is False


def test_hourly_exact_tick_is_due() -> None:
    job = _job(HourlySchedule(minute=30), timezone="UTC")
    now = datetime(2026, 10, 2, 9, 30, 0, 0, tzinfo=UTC)
    fire = next_run(job, last_run=None, now=now)
    assert fire.due is True
    assert fire.upcoming == datetime(2026, 10, 2, 10, 30, tzinfo=UTC)


def test_daily_next_boundary() -> None:
    job = _job(DailySchedule(hour=9, minute=0), timezone="UTC")
    now = datetime(2026, 10, 2, 10, 0, tzinfo=UTC)
    fire = next_run(job, last_run=None, now=now)
    assert fire.upcoming == datetime(2026, 10, 3, 9, 0, tzinfo=UTC)


def test_daily_exact_tick_is_due() -> None:
    job = _job(DailySchedule(hour=9, minute=0), timezone="UTC")
    now = datetime(2026, 10, 2, 9, 0, 0, 0, tzinfo=UTC)
    fire = next_run(job, last_run=None, now=now)
    assert fire.due is True
    assert fire.upcoming == datetime(2026, 10, 3, 9, 0, tzinfo=UTC)


def test_weekly_next_boundary() -> None:
    # 2026-10-02 是周五。weekday=0 是周一。now 是周五，下一档是下周一 09:00。
    job = _job(WeeklySchedule(weekday=0, hour=9, minute=0), timezone="UTC")
    now = datetime(2026, 10, 2, 10, 0, tzinfo=UTC)
    fire = next_run(job, last_run=None, now=now)
    assert fire.upcoming == datetime(2026, 10, 5, 9, 0, tzinfo=UTC)


def test_daily_skips_dst_gap_day() -> None:
    # 2026-03-08 America/New_York 春令时 02:00->03:00，02:30 不存在。
    # now 在 03-07，daily 02:30 的下一档必须跳过 03-08，落在 03-09。
    job = _job(DailySchedule(hour=2, minute=30), timezone=NY)
    now = datetime(2026, 3, 7, 23, 0, tzinfo=UTC)
    fire = next_run(job, last_run=None, now=now)
    assert fire.upcoming is not None
    assert fire.upcoming.year == 2026
    assert fire.upcoming.month == 3
    assert fire.upcoming.day == 9
    assert fire.upcoming.hour == 2
    assert fire.upcoming.minute == 30
    # upcoming 严格晚于 now，且是 NY 的 aware datetime。
    assert fire.upcoming > now
    assert fire.upcoming.tzinfo is not None


def test_weekly_skips_dst_gap_day() -> None:
    # 2026-03-08 是周日。weekly weekday=6（周日）02:30 在 03-08 不存在。
    # now 是 03-01（也周日）23:00 UTC。下一档应跳过 03-08，落在 03-15。
    job = _job(WeeklySchedule(weekday=6, hour=2, minute=30), timezone=NY)
    now = datetime(2026, 3, 1, 23, 0, tzinfo=UTC)
    fire = next_run(job, last_run=None, now=now)
    assert fire.upcoming is not None
    assert fire.upcoming.day == 15
    assert fire.upcoming.hour == 2
    assert fire.upcoming.minute == 30


def test_dst_fall_back_uses_fold_zero() -> None:
    # 2026-11-01 America/New_York 秋令时 02:00->01:00，01:30 出现两次。
    # daily 01:30 的 upcoming 应取 fold=0（第一次出现，EDT，-04:00）。
    job = _job(DailySchedule(hour=1, minute=30), timezone=NY)
    now = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
    fire = next_run(job, last_run=None, now=now)
    assert fire.upcoming is not None
    assert fire.upcoming.fold == 0
    assert fire.upcoming.utcoffset() == timedelta(hours=-4)


def test_naive_now_rejected() -> None:
    job = _job(OneShotSchedule(at=datetime(2026, 10, 3, 9, 0, tzinfo=UTC)))
    with pytest.raises(CronValidationError):
        next_run(job, last_run=None, now=datetime(2026, 10, 2, 9, 0))


def test_naive_last_run_rejected() -> None:
    job = _job(OneShotSchedule(at=datetime(2026, 10, 3, 9, 0, tzinfo=UTC)))
    with pytest.raises(CronValidationError):
        next_run(
            job, last_run=datetime(2026, 10, 1, 9, 0), now=datetime(2026, 10, 2, 9, 0, tzinfo=UTC)
        )


def test_same_input_same_output() -> None:
    job = _job(DailySchedule(hour=9, minute=0), timezone=NY)
    now = datetime(2026, 10, 2, 10, 0, tzinfo=UTC)
    first = next_run(job, last_run=None, now=now)
    second = next_run(job, last_run=None, now=now)
    assert first == second


def test_upcoming_always_strictly_after_now_property() -> None:
    """属性测试：任意合法 schedule + 随机 aware now，upcoming 要么为空要么严格晚于 now。"""
    rng = random.Random(20261002)  # noqa: S311 - 确定性属性测试，非密码学用途
    base = datetime(2026, 1, 1, tzinfo=UTC)
    schedules = (
        OneShotSchedule(at=datetime(2026, 6, 1, 9, 0, tzinfo=UTC)),
        IntervalSchedule(every_seconds=3600),
        HourlySchedule(minute=rng.randint(0, 59)),
        DailySchedule(hour=rng.randint(0, 23), minute=rng.randint(0, 59)),
        WeeklySchedule(
            weekday=rng.randint(0, 6), hour=rng.randint(0, 23), minute=rng.randint(0, 59)
        ),
    )
    for schedule in schedules:
        job = _job(schedule, timezone=NY)
        for _ in range(50):
            now = base + timedelta(days=rng.randint(0, 500), seconds=rng.randint(0, 86399))
            last_run = (
                now - timedelta(seconds=rng.randint(60, 86400))
                if schedule.kind != "oneshot" and rng.random() < 0.5
                else None
            )
            fire = next_run(job, last_run=last_run, now=now)
            if fire.upcoming is not None:
                assert fire.upcoming > now, f"{schedule.kind} upcoming not after now: {fire}"
                assert fire.upcoming.tzinfo is not None
            assert fire == next_run(job, last_run=last_run, now=now)
