"""Cron domain service (ADR-0268 §5, §6, §10).

提供 cron 工具与 HTTP 层共用的领域逻辑：新建任务、读取定义、
「即将到来」投影、整份覆盖、删除。``anchor_at`` 由服务端在
``cron.add`` 时写入；重复 id 返回现有记录不覆盖。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from lca.contracts.models.cron.models import (
    AgentExecution,
    ChatDelivery,
    CronJob,
    CronListItem,
    CronRun,
    DailySchedule,
    HourlySchedule,
    IntervalSchedule,
    OneShotSchedule,
    SpaceActionExecution,
    WeeklySchedule,
)
from lca.domain.cron.next_run import next_run
from lca.domain.cron.store import CronStore

__all__ = ["CronService"]

_WEEKDAYS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")


def _format_local(dt: datetime | None, tz_name: str) -> str | None:
    """把 aware datetime 格式化为其时区墙钟 ``YYYY-MM-DD HH:MM``。"""
    if dt is None:
        return None
    local = dt.astimezone(ZoneInfo(tz_name))
    return local.strftime("%Y-%m-%d %H:%M")


def _schedule_label(job: CronJob) -> str:
    schedule = job.schedule
    if isinstance(schedule, OneShotSchedule):
        local = schedule.at.astimezone(ZoneInfo(job.timezone))
        return f"一次性 {local.strftime('%Y-%m-%d %H:%M')}"
    if isinstance(schedule, IntervalSchedule):
        return f"每 {schedule.every_seconds} 秒"
    if isinstance(schedule, HourlySchedule):
        return f"每小时 {schedule.minute:02d} 分"
    if isinstance(schedule, DailySchedule):
        return f"每天 {schedule.hour:02d}:{schedule.minute:02d}"
    if isinstance(schedule, WeeklySchedule):
        return f"每周{_WEEKDAYS[schedule.weekday]} {schedule.hour:02d}:{schedule.minute:02d}"
    return schedule.kind


def _latest_run(runs: list[CronRun]) -> CronRun | None:
    """取最近一条 run（按 ``finished_at`` 时间戳，空视为最早）。"""
    if not runs:
        return None
    return max(runs, key=lambda r: r.finished_at.timestamp() if r.finished_at else 0.0)


# 回执状态汇总优先级（ADR-0268 §10）：最严重的优先。
_DELIVERY_PRIORITY: tuple[Literal["delivered", "failed", "silent", "not_sent"], ...] = (
    "failed",
    "delivered",
    "silent",
    "not_sent",
)


def _summary_last_delivery(
    run: CronRun | None,
) -> Literal["delivered", "failed", "silent", "not_sent"] | None:
    """按 ADR-0268 §10 汇总多个目标回执为一个 ``last_delivery``。"""
    if run is None or not run.receipts:
        return None
    states = {receipt.state for receipt in run.receipts}
    # receipt.state 是闭集 Literal；任一状态必命中其一分支。
    return next((s for s in _DELIVERY_PRIORITY if s in states), None)


class CronService:
    """cron 定义与「即将到来」投影的领域逻辑。"""

    def __init__(self, store: CronStore) -> None:
        self._store = store

    def add_job(
        self,
        *,
        id: str,
        title: str,
        schedule: OneShotSchedule
        | IntervalSchedule
        | HourlySchedule
        | DailySchedule
        | WeeklySchedule,
        timezone: str,
        body: str,
        execution: AgentExecution | SpaceActionExecution,
        delivery_targets: tuple[ChatDelivery, ...],
        report: Literal["always", "anomalies_only"],
        owner: str,
        created_chat_id: str,
        now: datetime,
        enabled: bool = True,
        max_retries: int = 0,
        timeout_seconds: int | None = None,
    ) -> CronJob:
        """新建任务；重复 id 返回现有记录，不覆盖。"""
        existing = self._store.get_job(id)
        if existing is not None:
            return existing
        job = CronJob(
            id=id,
            title=title,
            schedule=schedule,
            timezone=timezone,
            body=body,
            execution=execution,
            delivery_targets=delivery_targets,
            report=report,
            owner=owner,
            created_chat_id=created_chat_id,
            anchor_at=now,
            enabled=enabled,
            max_retries=max_retries,
            timeout_seconds=timeout_seconds,
        )
        self._store.save_job(job)
        return job

    def get_job(self, job_id: str) -> CronJob | None:
        return self._store.get_job(job_id)

    def get_run_records(self, job_id: str) -> list[CronRun]:
        return self._store.list_runs(job_id)

    def list_items(
        self,
        owner: str | None = None,
        *,
        now: datetime,
        allow_owners: tuple[str, ...] = (),
    ) -> list[CronListItem]:
        """生成「即将到来」投影列表。"""
        items: list[CronListItem] = []
        valid_owners = {owner} if owner is not None else set()
        valid_owners.update(allow_owners)

        for job in self._store.list_jobs():
            if valid_owners and job.owner not in valid_owners:
                continue
            # 已完成且未被推迟至未来的单次任务不进入即将到来。回执为空表示
            # handoff 轮还没做出投递决定（ADR-0268 §6），这种任务必须留在列表
            # 上，否则一次没送达的触发连「未决」都显示不出来就消失了。
            runs = self._store.list_runs(job.id)
            latest = _latest_run(runs)
            if (
                job.schedule.kind == "oneshot"
                and latest is not None
                and latest.finished_at is not None
                and job.schedule.at <= latest.finished_at
                and latest.receipts
            ):
                continue
            last_run_dt = latest.finished_at if latest is not None else None
            fire = next_run(job, last_run=last_run_dt, now=now)
            upcoming = fire.upcoming
            due = fire.due
            if not job.enabled:
                due = False
            items.append(
                CronListItem(
                    id=job.id,
                    title=job.title,
                    schedule_label=_schedule_label(job),
                    next_run_local=_format_local(upcoming, job.timezone),
                    due=due,
                    enabled=job.enabled,
                    last_run_local=_format_local(last_run_dt, job.timezone),
                    last_delivery=_summary_last_delivery(latest),
                )
            )
        return items

    def replace_job(self, job: CronJob) -> None:
        """整份覆盖存储里的定义（模型路径先 ``cron.view`` 再覆盖）。"""
        self._store.save_job(job)

    def remove_job(self, job_id: str) -> bool:
        """删除定义与未注入 handoff；不删除已结束的 run 记录。"""
        return self._store.delete_job(job_id)
