"""CronScheduler：ADR-0268 §7、§8 的 tick 调度器（P3）。

职责：``tick(now)`` 遍历 assistant home 下的 ``cron/*.json`` 定义，按
``next_run`` 的 ``due`` 启动 worker；文件锁互斥 + 心跳 + stale 收割复用
:class:`lca.infrastructure.proactive.scheduler.ProactiveScheduler` 的模式；
同一 ``job_id`` 运行中的 run 不杀，排队槽只留最新一次，旧排队项记
``superseded`` + ``not_sent``。

本模块只做控制面：worker 结束后追加 :class:`CronRun`（``receipts`` 为空
表示未决），不在这里注入 handoff。时钟由调用方传入，保持 C8 确定性。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import socket
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lca.contracts.models.cron.models import (
    CronJob,
    CronRun,
    CronValidationError,
    TargetReceipt,
)
from lca.domain.cron.next_run import next_run
from lca.domain.cron.store import CronStore
from lca.domain.cron.worker_context import (
    WorkerProductContext,
    assemble_worker_context,
)

_log = logging.getLogger(__name__)

# ADR-0263 §9②：stale 绝对上限 90 分钟，与主动消息调度器一致。
STALE_ABSOLUTE_CAP_S = 90 * 60

# ``agent`` 执行与 ``space_action`` 重试耗尽后的最长自然超时（ADR-0268 §7）。
_MAX_TIMEOUT_S = 86400

WorkerRunner = Callable[[str], Awaitable[Any]]
Clock = Callable[[], datetime]


@dataclass(frozen=True, slots=True)
class CronTickReport:
    """一次 ``tick`` 的摘要，供调用方观测调度行为。"""

    tick_at: datetime
    lock_acquired: bool
    due: int = 0
    started: int = 0
    queued: int = 0
    superseded: int = 0


class CronScheduler:
    """文件锁互斥的 cron tick 调度器（ADR-0268 §7、§8）。"""

    def __init__(
        self,
        *,
        store: CronStore,
        lock_dir: str | Path,
        workspace_path: str,
        worker_runner: WorkerRunner,
        default_interval_s: int = 60,
        clock: Clock | None = None,
    ) -> None:
        self._store = store
        self._lock_dir = Path(lock_dir)
        self._workspace_path = workspace_path
        self._worker_runner = worker_runner
        self._default_interval_s = default_interval_s
        self._clock = clock if clock is not None else (lambda: datetime.now(UTC))
        # 进程内存中的运行态（ADR-0268 §8）：调度器单实例运行。
        self._active: dict[str, asyncio.Task] = {}
        self._pending: dict[str, str] = {}

    # ---- 对外入口：carrier 每次 tick 调用一次 ----

    async def tick(self, now: datetime) -> CronTickReport:
        """遍历任务定义，``due`` 的任务启动 worker；返回 tick 摘要。

        ``now`` 必须是 aware datetime（调用方注入时钟）。锁未取得时返回
        ``lock_acquired=False`` 的摘要，不执行任何调度。
        """
        now_ms = int(now.timestamp() * 1000)
        if not self._acquire_lock(now_ms):
            return CronTickReport(tick_at=now, lock_acquired=False)

        due = started = queued = superseded = 0
        try:
            for job in self._store.list_jobs():
                if not job.enabled:
                    continue
                fire = self._fire_for(job, now)
                if not fire:
                    continue
                due += 1
                run_id = self._new_run_id(job)
                if job.id in self._active:
                    # 运行中的 run 不杀：新的到点写入排队槽，槽里更早的取消。
                    old_pending = self._pending.get(job.id)
                    if old_pending is not None:
                        self._record_superseded(job.id, old_pending, now)
                        superseded += 1
                    self._pending[job.id] = run_id
                    queued += 1
                else:
                    self._start_worker(job, run_id)
                    started += 1
            return CronTickReport(
                tick_at=now,
                lock_acquired=True,
                due=due,
                started=started,
                queued=queued,
                superseded=superseded,
            )
        finally:
            self.release_lock()

    async def wait_idle(self) -> None:
        """等待全部运行中的 worker 结束（测试与关停用）。

        运行中的 worker 结束后，若排队槽有待跑项会立刻启动，因此这里循环
        直到 ``_active`` 清空。
        """
        while self._active:
            tasks = tuple(self._active.values())
            await asyncio.gather(*tasks, return_exceptions=True)

    # ---- 单 job 的触发判定 ----

    def _fire_for(self, job: CronJob, now: datetime) -> bool | None:
        """计算 ``next_run``；单条坏定义不使整个 tick 失败。"""
        try:
            last_run = self._latest_finished_at(job.id)
            return next_run(job, last_run=last_run, now=now).due
        except CronValidationError:
            _log.warning("cron.job_skipped job_id=%s", job.id, exc_info=True)
            return None

    def _latest_finished_at(self, job_id: str) -> datetime | None:
        """最近一条 run 的 ``finished_at``；无 run 返回 ``None``。"""
        runs = self._store.list_runs(job_id)
        if not runs:
            return None
        latest = max(runs, key=lambda r: r.finished_at.timestamp() if r.finished_at else 0.0)
        return latest.finished_at

    # ---- worker 启动与执行 ----

    def _new_run_id(self, job: CronJob) -> str:
        return f"{job.id}-{uuid.uuid4().hex}"

    def _product_context(self, job: CronJob, run_id: str) -> WorkerProductContext:
        return WorkerProductContext(
            job_id=job.id,
            owner=job.owner,
            workspace_path=self._workspace_path,
            timezone=job.timezone,
            report=job.report,
            delivery_targets=job.delivery_targets,
            run_id=run_id,
        )

    def _start_worker(self, job: CronJob, run_id: str) -> None:
        self._active[job.id] = asyncio.create_task(self._run_worker(job, run_id))

    async def _run_worker(self, job: CronJob, run_id: str) -> None:
        """执行带重试的 worker，写 run 记录，然后接手排队槽。"""
        try:
            outcome = await self._execute_with_retries(job, run_id)
            self._store.append_run(
                job.id,
                CronRun(
                    run_id=run_id,
                    outcome=outcome,
                    receipts=(),
                    finished_at=self._clock(),
                ),
            )
        except Exception:
            # 意外错误（如落盘失败）也不让 worker 任务带着异常结束。
            _log.exception("cron.worker_crashed job_id=%s run_id=%s", job.id, run_id)
            with contextlib.suppress(Exception):
                self._store.append_run(
                    job.id,
                    CronRun(
                        run_id=run_id,
                        outcome="runtime_failure",
                        receipts=(),
                        finished_at=self._clock(),
                    ),
                )
        finally:
            self._active.pop(job.id, None)
            pending = self._pending.pop(job.id, None)
            if pending is not None:
                self._start_worker(job, pending)

    async def _execute_with_retries(self, job: CronJob, run_id: str) -> str:
        """按 ``max_retries`` 重试 ``runtime_failure`` / ``timed_out``。

        重试使用同一个 ``run_id``（ADR-0268 §7）；``completed`` 立即返回。
        """
        text = assemble_worker_context(job.body, self._product_context(job, run_id))
        outcome = "runtime_failure"
        for attempt in range(job.max_retries + 1):
            outcome = await self._execute_once(job, run_id, text)
            if outcome == "completed":
                return outcome
            if attempt < job.max_retries:
                _log.warning(
                    "cron.worker_retry job_id=%s run_id=%s attempt=%d outcome=%s",
                    job.id,
                    run_id,
                    attempt + 1,
                    outcome,
                )
        return outcome

    async def _execute_once(self, job: CronJob, run_id: str, text: str) -> str:
        """跑一次 worker；超时记 ``timed_out``，异常记 ``runtime_failure``。"""
        timeout = self._effective_timeout(job)
        try:
            if timeout is None:
                await self._worker_runner(text)
            else:
                await asyncio.wait_for(self._worker_runner(text), timeout=timeout)
            return "completed"
        except TimeoutError:
            _log.warning(
                "cron.worker_timed_out job_id=%s run_id=%s timeout=%s",
                job.id,
                run_id,
                timeout,
            )
            return "timed_out"
        except Exception:
            _log.exception("cron.worker_runtime_failure job_id=%s run_id=%s", job.id, run_id)
            return "runtime_failure"

    def _effective_timeout(self, job: CronJob) -> int | None:
        """ADR-0268 §7 的实际超时秒数。

        ``min(86400, max(timeout_seconds 或 gap_seconds, gap_seconds))``；
        一次性任务没有自然间隔，未声明时上限 86400。
        """
        gap = self._gap_seconds(job)
        declared = job.timeout_seconds
        if declared is None:
            if gap is None:
                return _MAX_TIMEOUT_S
            return min(_MAX_TIMEOUT_S, gap)
        if gap is None:
            return min(_MAX_TIMEOUT_S, declared)
        return min(_MAX_TIMEOUT_S, max(declared, gap))

    @staticmethod
    def _gap_seconds(job: CronJob) -> int | None:
        kind = job.schedule.kind
        if kind == "interval":
            return job.schedule.every_seconds
        if kind == "hourly":
            return 3600
        if kind == "daily":
            return 86400
        if kind == "weekly":
            return 604800
        return None  # oneshot

    # ---- run 记录 ----

    def _record_superseded(self, job_id: str, run_id: str, now: datetime) -> None:
        self._store.append_run(
            job_id,
            CronRun(
                run_id=run_id,
                outcome="superseded",
                receipts=(TargetReceipt(chat_id=None, state="not_sent"),),
                finished_at=now,
            ),
        )

    # ---- 文件锁（ADR-0263 §9①②，与 ProactiveScheduler 同模式） ----

    @property
    def _lock_file(self) -> Path:
        return self._lock_dir / "cron.lock"

    def _acquire_lock(self, now_ms: int) -> bool:
        self._lock_dir.mkdir(parents=True, exist_ok=True)
        owner = f"{socket.gethostname()}:{os.getpid()}"
        try:
            with open(self._lock_file, "x", encoding="utf-8") as f:
                json.dump({"owner": owner, "mtime_ms": now_ms}, f)
            return True
        except FileExistsError:
            pass
        try:
            with open(self._lock_file, encoding="utf-8") as f:
                lock = json.load(f)
        except (OSError, ValueError):
            lock = {}
        mtime_ms = int(lock.get("mtime_ms", 0) or 0)
        stale_after_s = min(self._default_interval_s * 2.0, STALE_ABSOLUTE_CAP_S)
        if now_ms - mtime_ms > stale_after_s * 1000:
            _log.warning(
                "cron.lock_stale_reaped owner=%s age_s=%d",
                lock.get("owner"),
                (now_ms - mtime_ms) // 1000,
            )
            with contextlib.suppress(OSError):
                self._lock_file.unlink()
            return self._acquire_lock(now_ms)
        return False

    def release_lock(self) -> None:
        with contextlib.suppress(OSError):
            self._lock_file.unlink()


__all__ = [
    "STALE_ABSOLUTE_CAP_S",
    "CronScheduler",
    "CronTickReport",
]
