"""定时换装调度器（ADR-0269 §5）。

轻量 asyncio 后台循环（60s tick）复用 ``lca/domain/cron`` 的 ``CronStore``
与 ``next_run``：扫描 ``execution.kind == "space_action"`` 且
``execution.artifact_id == "avatar"`` 的启用任务，到期时调用
``AvatarService.edit(owner, body, auto_activate=True)`` 立即换装，并追加一条
``CronRun`` 回执。单个任务失败只记 ``runtime_failure``，不中断整个循环。

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

from lca.contracts.models.cron.models import CronJob
from lca.domain.cron.next_run import next_run
from lca.domain.cron.store import CronStore

logger = logging.getLogger(__name__)

_NOTIFICATION_TEXT = "定时换装完成：{body}"


class AvatarCostumeScheduler:
    def __init__(
        self,
        service,
        cron_store: CronStore,
        tick_seconds: int = 60,
        notifier: Callable[[str, str], None] | None = None,
    ) -> None:
        self.service = service
        self.cron_store = cron_store
        self.tick_seconds = tick_seconds
        self._notifier = notifier
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

    async def _tick(self) -> None:
        jobs = self._select_avatar_jobs(self.cron_store.list_jobs())
        now = datetime.now(UTC)
        for job in jobs:
            try:
                await self._process_job(job, now)
            except Exception:
                # 单条任务失败（读 run 记录 / next_run / 落盘）不使整个 tick 失败。
                logger.exception("avatar scheduler job failed job_id=%s", job.id)

    async def _process_job(self, job: CronJob, now: datetime) -> None:
        runs = self.cron_store.get_run_records(job.id)
        last_run = runs[-1].finished_at if runs and runs[-1].finished_at else None
        fire = next_run(job, last_run=last_run, now=now)
        if not fire.due:
            return
        try:
            await self.service.edit(job.owner, job.body, auto_activate=True)
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

    async def run_forever(self) -> None:
        """每 ``tick_seconds`` 执行一次扫描；``stop()`` 后退出。"""
        while not self._stop.is_set():
            try:
                await self._tick()
            except Exception:
                logger.exception("avatar scheduler tick failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.tick_seconds)
            except TimeoutError:
                continue


__all__ = ["AvatarCostumeScheduler"]
