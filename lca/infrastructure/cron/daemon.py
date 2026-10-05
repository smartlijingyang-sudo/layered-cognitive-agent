from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lca.domain.cron.store import CronStore
from lca.infrastructure.cron.scheduler import CronScheduler, CronTickReport
from lca.infrastructure.cron.worker_runner import CronWorkerRunner

_log = logging.getLogger(__name__)


class CronDaemonService:
    """常驻后台 Cron 调度守护服务（ADR-0268 生产运行态）。

    在应用生命周期（如 Starlette Lifespan）中拉起，提供：
    1. 定时 Tick（默认 15s 精度）；
    2. 文件锁多实例互斥与自动收割；
    3. 开机自愈与智能补偿；
    4. 优雅停机与任务等待。
    """

    def __init__(
        self,
        *,
        store: CronStore,
        lock_dir: str | Path,
        workspace_path: str,
        worker_runner: Callable[[str], Any] | None = None,
        tick_interval_s: int = 15,
        clock: Callable[[], datetime] | None = None,
        handoff_dispatcher: Any | None = None,
    ) -> None:
        self._store = store
        self._lock_dir = Path(lock_dir)
        self._workspace_path = workspace_path
        self._tick_interval_s = max(1, tick_interval_s)
        self._clock = clock or (lambda: datetime.now(UTC))

        if worker_runner is not None:
            self._worker_runner = worker_runner
        else:
            self._worker_runner = CronWorkerRunner(store=store)

        self._scheduler = CronScheduler(
            store=self._store,
            lock_dir=self._lock_dir,
            workspace_path=self._workspace_path,
            worker_runner=self._worker_runner,
            default_interval_s=self._tick_interval_s,
            handoff_dispatcher=handoff_dispatcher,
            clock=self._clock,
        )

        self._task: asyncio.Task[None] | None = None
        self._is_running = False

    @property
    def is_running(self) -> bool:
        return self._is_running

    async def start(self) -> None:
        """启动后台定时调度协程。"""
        if self._is_running:
            return
        self._is_running = True
        self._task = asyncio.create_task(self._run_loop(), name="cron_daemon_loop")
        _log.info(
            "cron.daemon_started interval_s=%d lock_dir=%s",
            self._tick_interval_s,
            self._lock_dir,
        )

    async def stop(self) -> None:
        """优雅关闭后台调度器并释放锁。"""
        if not self._is_running:
            return
        self._is_running = False
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

        await self._scheduler.wait_idle()
        self._scheduler.release_lock()
        _log.info("cron.daemon_stopped")

    async def tick(self, now: datetime | None = None) -> CronTickReport:
        """手动触发一次 Tick，返回报告。"""
        current = now or self._clock()
        return await self._scheduler.tick(current)

    async def _run_loop(self) -> None:
        """后台轮询循环。"""
        while self._is_running:
            try:
                now = self._clock()
                report = await self._scheduler.tick(now)
                if report.due > 0 or report.started > 0:
                    _log.info(
                        "cron.tick_report due=%d started=%d queued=%d superseded=%d",
                        report.due,
                        report.started,
                        report.queued,
                        report.superseded,
                    )
            except asyncio.CancelledError:
                break
            except Exception:
                _log.exception("cron.daemon_loop_error")

            try:
                await asyncio.sleep(self._tick_interval_s)
            except asyncio.CancelledError:
                break
