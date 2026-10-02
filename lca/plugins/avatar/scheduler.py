"""定时换装调度器（ADR-0269 §5）。

轻量 asyncio 后台循环（60s tick）复用 ``lca/domain/cron`` 的 ``CronStore``
与 ``next_run``：扫描 ``execution.kind == "space_action"`` 且
``execution.artifact_id == "avatar"`` 的启用任务，到期时调用
``AvatarService.edit(owner, body, auto_activate=True)`` 立即换装，并追加一条
``CronRun`` 回执。单个任务失败只记 ``runtime_failure``，不中断整个循环。

服务按 assistant 懒解析（``service_resolver``）：每个助理有独立
``AvatarStore``（spec §5），调度器不能复用单一服务实例。

轻量通知：换装成功后经可选的 ``notifier(assistant_id, text)`` 钩子发送。
Task 10 装配时把它接到 :class:`ProactiveDeliverer`（``ProactiveMessage`` +
``DeliveryTarget(SESSION_APPEND)``）；未装配时通知为 no-op。头像实时同步
由 avatar WS 通道承载（``avatar_updated``），本钩子不新建推送通道。

ADR-0268 的正式 cron worker 落地后，本调度器可退役，由 worker 消费同一批
``CronJob``（``worker_context.py`` 已支持 ``SpaceActionExecution``）。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from typing import Any

from lca.contracts.models.cron.models import CronJob, CronRun
from lca.domain.cron.next_run import next_run
from lca.domain.cron.store import CronStore

logger = logging.getLogger(__name__)

_NOTIFICATION_TEXT = "定时换装完成：{body}"

_DEFAULT_CLEANUP_INTERVAL_SECONDS = 3600


def _latest_run(runs: list[CronRun]) -> CronRun | None:
    """取最近一条 run（按 ``finished_at`` 时间戳，空视为最早；ADR-0268）。

    run 记录按 run_id 字典序落盘，不保证时间有序，不能取 ``runs[-1]``。
    """
    if not runs:
        return None
    return max(runs, key=lambda r: r.finished_at.timestamp() if r.finished_at else 0.0)


class AvatarCostumeScheduler:
    def __init__(
        self,
        service_resolver: Callable[[str], Any],
        cron_store: CronStore,
        tick_seconds: int = 60,
        notifier: Callable[[str, str], None] | None = None,
        cleanup_interval_seconds: int = _DEFAULT_CLEANUP_INTERVAL_SECONDS,
    ) -> None:
        self.service_resolver = service_resolver
        self.cron_store = cron_store
        self.tick_seconds = tick_seconds
        self._notifier = notifier
        self._cleanup_interval_seconds = cleanup_interval_seconds
        self._last_cleanup: datetime | None = None
        self._stop = asyncio.Event()

    @staticmethod
    def _select_avatar_jobs(jobs: Iterable[CronJob]) -> list[CronJob]:
        return [
            job
            for job in jobs
            if job.enabled
            and job.execution.kind == "space_action"
            and job.execution.artifact_id == "avatar"
        ]

    def _maybe_cleanup(self, now: datetime) -> None:
        """按小时间隔清理各助理 avatar 目录的过期候选（spec §5）。

        ``cleanup_expired`` 是同步磁盘 I/O，只在间隔边界执行一次，避免拖慢
        每个 tick；cron_store 未实现该方法（如测试用 CronStore）时 no-op。
        """
        if (
            self._last_cleanup is not None
            and (now - self._last_cleanup).total_seconds() < self._cleanup_interval_seconds
        ):
            return
        self._last_cleanup = now
        cleanup = getattr(self.cron_store, "cleanup_expired", None)
        if cleanup is None:
            return
        try:
            cleanup(now)
        except Exception:
            logger.exception("avatar cleanup_expired failed")

    async def _tick(self) -> None:
        now = datetime.now(UTC)
        self._maybe_cleanup(now)
        jobs = self._select_avatar_jobs(self.cron_store.list_jobs())
        for job in jobs:
            try:
                await self._process_job(job, now)
            except Exception:
                # 单条任务失败（读 run 记录 / next_run / 落盘）不使整个 tick 失败。
                logger.exception("avatar scheduler job failed job_id=%s", job.id)

    async def _process_job(self, job: CronJob, now: datetime) -> None:
        runs = self.cron_store.get_run_records(job.id)
        latest = _latest_run(runs)
        last_run_dt = latest.finished_at if latest is not None else None
        fire = next_run(job, last_run=last_run_dt, now=now)
        if not fire.due:
            return
        try:
            service = self.service_resolver(job.owner)
            await service.edit(job.owner, job.body, auto_activate=True)
            self.cron_store.append_run(
                job.id,
                outcome="completed",
                finished_at=datetime.now(UTC),
            )
            self._notify(job.owner, _NOTIFICATION_TEXT.format(body=job.body))
        except Exception:
            logger.exception("avatar costume change failed job_id=%s", job.id)
            self.cron_store.append_run(
                job.id,
                outcome="runtime_failure",
                finished_at=datetime.now(UTC),
            )

    def _notify(self, assistant_id: str, text: str) -> None:
        if self._notifier is None:
            return
        try:
            self._notifier(assistant_id, text)
        except Exception:
            logger.exception(
                "avatar costume change notification failed assistant_id=%s", assistant_id
            )

    def stop(self) -> None:
        """请求 ``run_forever`` 在下一个 tick 边界退出（测试与关停用）。"""
        self._stop.set()

    @staticmethod
    def _seconds_until_boundary(now: datetime, tick_seconds: int) -> float:
        """距下一个 ``tick_seconds`` 墙钟边界的秒数。

        ``next_run`` 的 daily/hourly/weekly 判定要求 ``second == 0`` 且
        ``microsecond == 0``；固定相位偏移的循环（如永远落在 ``.123456``）
        会永久错过该瞬间。按墙钟秒边界对齐后，60s 循环总在 ``:00.000``
        醒来，消除系统性的相位偏移。
        """
        seconds_into_period = now.second + now.microsecond / 1_000_000
        return tick_seconds - (seconds_into_period % tick_seconds)

    async def run_forever(self) -> None:
        """每 ``tick_seconds`` 扫描一次，并把唤醒对齐到墙钟秒边界。

        对齐到边界（60s tick 落在 ``:00.000``）避免 ``next_run`` 的
        ``second == 0 and microsecond == 0`` 判定被相位偏移永久错过；
        ``stop()`` 可随时中断对齐等待。
        """
        while not self._stop.is_set():
            try:
                await self._tick()
            except Exception:
                logger.exception("avatar scheduler tick failed")
            delay = self._seconds_until_boundary(datetime.now(UTC), self.tick_seconds)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=delay)
            except TimeoutError:
                continue


__all__ = ["AvatarCostumeScheduler", "_latest_run"]
