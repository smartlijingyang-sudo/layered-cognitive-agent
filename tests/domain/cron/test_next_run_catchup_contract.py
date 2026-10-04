"""todo-47: ``next_run`` 触发档"跨越式" due 契约（待 ADR-0268 修正案）。

缺陷（2026-10-05 00:09 arch 轮立案，实证见 ADR-0287 / 21d8aec53 message）：
interval/hourly/daily/weekly 四种周期调度以**微秒级 datetime 相等**判 due；
daemon 在 ``asyncio.sleep`` 后采样的 ``datetime.now(UTC)`` 几乎不可能恰好
落在触发档的零微秒上 → 周期任务永不触发（真机实测：tick 1s / every 5s，
30 秒内触发 0 次；同 store 的 oneshot 触发 1 次）。

本文件钉住"跨越式"语义：采样时刻已越过触发档、且 last_run 尚未服务该档
时，due 必须为 True。当前相等语义下 xfail 的 5 例全部 FAIL —— 用
``xfail(strict=True)`` 钉在 main 上：套件保持绿；语义修（``<=``/跨越式）
一落地，XPASS(strict) 立刻变红，强制修法 commit 摘掉 marker。
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
    WeeklySchedule,
)
from lca.domain.cron.next_run import next_run

_XFAIL_TODO47 = pytest.mark.xfail(
    strict=True,
    reason="todo-47: next_run 以微秒相等判 due;跨越式 due 待 ADR-0268 修正案+语义修",
)


def _job(schedule: object, *, timezone: str = "UTC") -> CronJob:
    return CronJob(
        id="job_catchup",
        title="周期提醒",
        schedule=schedule,  # type: ignore[arg-type]
        timezone=timezone,
        body="b",
        execution=AgentExecution(),
        delivery_targets=(ChatDelivery(chat_id="chat_1"),),
        owner="user_1",
        created_chat_id="chat_1",
        anchor_at=datetime(2026, 10, 2, 9, 0, tzinfo=UTC),
    )


def test_exact_slot_sample_still_due_after_fix() -> None:
    """对照：恰好落在档上的采样今天 due，修语义后（``<=`` 含相等）必须继续 due。"""
    job = _job(IntervalSchedule(every_seconds=3600))
    fire = next_run(job, last_run=None, now=datetime(2026, 10, 2, 10, 0, tzinfo=UTC))
    assert fire.due is True


@_XFAIL_TODO47
def test_interval_due_when_sampled_just_after_slot() -> None:
    """daemon 采样晚 123456µs：10:00 档已过、未服务 → due 必须 True。"""
    job = _job(IntervalSchedule(every_seconds=3600))
    fire = next_run(
        job,
        last_run=None,
        now=datetime(2026, 10, 2, 10, 0, 0, 123456, tzinfo=UTC),
    )
    assert fire.due is True


@_XFAIL_TODO47
def test_interval_due_when_sleep_overshoots_one_slot() -> None:
    """asyncio.sleep 飘 0.9s：last_run=09:00，10:00 档被跳过 → due 必须 True。"""
    job = _job(IntervalSchedule(every_seconds=3600))
    fire = next_run(
        job,
        last_run=datetime(2026, 10, 2, 9, 0, tzinfo=UTC),
        now=datetime(2026, 10, 2, 10, 0, 0, 900000, tzinfo=UTC),
    )
    assert fire.due is True


@_XFAIL_TODO47
def test_hourly_due_when_sampled_just_after_minute() -> None:
    """整点过 0.5s 采样：10:15 档已过 → due 必须 True。"""
    job = _job(HourlySchedule(minute=15))
    fire = next_run(
        job,
        last_run=None,
        now=datetime(2026, 10, 2, 10, 15, 0, 500000, tzinfo=UTC),
    )
    assert fire.due is True


@_XFAIL_TODO47
def test_daily_due_when_sampled_just_after_slot() -> None:
    """09:30 过 2s 采样：当日档已过 → due 必须 True。"""
    job = _job(DailySchedule(hour=9, minute=30))
    fire = next_run(
        job,
        last_run=None,
        now=datetime(2026, 10, 2, 9, 30, 2, tzinfo=UTC),
    )
    assert fire.due is True


@_XFAIL_TODO47
def test_weekly_due_when_sampled_just_after_slot() -> None:
    """2026-10-02 是周五；09:00 过 0.25s 采样：本周档已过 → due 必须 True。"""
    job = _job(WeeklySchedule(weekday=4, hour=9, minute=0))
    fire = next_run(
        job,
        last_run=None,
        now=datetime(2026, 10, 2, 9, 0, 0, 250000, tzinfo=UTC),
    )
    assert fire.due is True
