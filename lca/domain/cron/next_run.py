"""``next_run`` pure function (ADR-0268 §5).

时钟由调用方传入。本模块不读时钟、不读 ``enabled``、不做 I/O。
同一输入两次调用结果相同。naive datetime 拒绝；非法 timezone 抛
类型化 :class:`CronValidationError`，不抛裸异常。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from lca.contracts.models.cron.models import (
    CronJob,
    CronValidationError,
    DailySchedule,
    HourlySchedule,
    IntervalSchedule,
    NextFire,
    OneShotSchedule,
    WeeklySchedule,
    wall_clock_exists,
)

__all__ = ["next_run"]


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CronValidationError(f"{name} must be timezone-aware")


def next_run(
    job: CronJob,
    last_run: datetime | None,
    now: datetime,
) -> NextFire:
    """计算任务的下一触发档。

    - ``job`` 是任务定义；``schedule.kind`` 决定推进规则。
    - ``last_run`` 为 None 表示尚未运行过；否则从 ``last_run`` 之后推进。
    - ``now`` 必须是 aware datetime。调用方负责注入时钟。
    - 返回的 ``upcoming`` 严格晚于 ``now``；``due`` 表示这一刻要触发。
    """
    _require_aware(now, "now")
    if last_run is not None:
        _require_aware(last_run, "last_run")
    try:
        tz = ZoneInfo(job.timezone)
    except Exception as exc:
        raise CronValidationError(f"invalid timezone: {job.timezone!r}") from exc

    now_local = now.astimezone(tz)
    schedule = job.schedule

    if isinstance(schedule, OneShotSchedule):
        at = schedule.at.astimezone(tz)
        if last_run is not None:
            return NextFire(upcoming=None, due=False)
        if at > now_local:
            return NextFire(upcoming=at, due=False)
        return NextFire(upcoming=None, due=True)

    if isinstance(schedule, IntervalSchedule):
        delta = timedelta(seconds=schedule.every_seconds)
        if last_run is None:
            candidate = job.anchor_at.astimezone(tz) + delta
        else:
            candidate = last_run.astimezone(tz) + delta
        if candidate == now_local:
            return NextFire(upcoming=candidate + delta, due=True)
        while candidate < now_local:
            candidate += delta
            if candidate == now_local:
                return NextFire(upcoming=candidate + delta, due=True)
        return NextFire(upcoming=candidate, due=False)

    if isinstance(schedule, HourlySchedule):
        due = (
            now_local.minute == schedule.minute
            and now_local.second == 0
            and now_local.microsecond == 0
        )
        return NextFire(
            upcoming=_next_hourly(now_local, schedule.minute, tz),
            due=due,
        )

    if isinstance(schedule, DailySchedule):
        due = (
            now_local.hour == schedule.hour
            and now_local.minute == schedule.minute
            and now_local.second == 0
            and now_local.microsecond == 0
        )
        return NextFire(
            upcoming=_next_daily(now_local, schedule.hour, schedule.minute, tz),
            due=due,
        )

    if isinstance(schedule, WeeklySchedule):
        due = (
            now_local.weekday() == schedule.weekday
            and now_local.hour == schedule.hour
            and now_local.minute == schedule.minute
            and now_local.second == 0
            and now_local.microsecond == 0
        )
        return NextFire(
            upcoming=_next_weekly(
                now_local,
                schedule.weekday,
                schedule.hour,
                schedule.minute,
                tz,
            ),
            due=due,
        )

    raise CronValidationError(f"unknown schedule kind: {schedule.kind!r}")


def _next_hourly(
    now_local: datetime,
    minute: int,
    tz: ZoneInfo,
) -> datetime:
    """严格晚于 ``now_local`` 的下一档小时触发点（墙钟存在）。

    缺口里不存在的本地时刻不作为结果；取缺口之后的下一档真实分钟。
    秋令时歧义取 ``fold=0``。
    """
    candidate = now_local.replace(
        minute=minute,
        second=0,
        microsecond=0,
        fold=0,
    )
    if candidate <= now_local:
        candidate += timedelta(hours=1)
        candidate = candidate.replace(
            minute=minute,
            second=0,
            microsecond=0,
            fold=0,
        )
    while not wall_clock_exists(candidate):
        candidate += timedelta(hours=1)
        candidate = candidate.replace(
            minute=minute,
            second=0,
            microsecond=0,
            fold=0,
        )
    return candidate


def _next_daily(
    now_local: datetime,
    hour: int,
    minute: int,
    tz: ZoneInfo,
) -> datetime:
    """严格晚于 ``now_local`` 的下一档墙钟（日任务）。

    春令时缺口日跳过该日，取下一周期里真实存在的同一墙钟。
    """
    candidate = now_local.replace(
        hour=hour,
        minute=minute,
        second=0,
        microsecond=0,
        fold=0,
    )
    if candidate <= now_local:
        candidate += timedelta(days=1)
        candidate = candidate.replace(
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0,
            fold=0,
        )
    while not wall_clock_exists(candidate):
        candidate += timedelta(days=1)
        candidate = candidate.replace(
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0,
            fold=0,
        )
    return candidate


def _next_weekly(
    now_local: datetime,
    weekday: int,
    hour: int,
    minute: int,
    tz: ZoneInfo,
) -> datetime:
    """严格晚于 ``now_local`` 的下一档墙钟（周任务）。"""
    candidate = now_local.replace(
        hour=hour,
        minute=minute,
        second=0,
        microsecond=0,
        fold=0,
    )
    # 找到本周/下周里 weekday 对应的日期，再对齐墙钟。
    days_ahead = (weekday - candidate.weekday()) % 7
    candidate += timedelta(days=days_ahead)
    candidate = candidate.replace(
        hour=hour,
        minute=minute,
        second=0,
        microsecond=0,
        fold=0,
    )
    if candidate <= now_local:
        candidate += timedelta(days=7)
        candidate = candidate.replace(
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0,
            fold=0,
        )
    while not wall_clock_exists(candidate):
        candidate += timedelta(days=7)
        candidate = candidate.replace(
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0,
            fold=0,
        )
    return candidate
