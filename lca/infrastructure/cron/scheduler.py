"""CronScheduler：ADR-0268 §7、§8 的 tick 调度器（P3）。

职责：``tick(now)`` 遍历 assistant home 下的 ``cron/*.json`` 定义，按
``next_run`` 的 ``due`` 启动 worker；文件锁互斥 + 心跳 + stale 收割由
:class:`lca.infrastructure.scheduler_file_lock.SchedulerFileLock` 提供
（与 ``ProactiveScheduler`` 共享实现）；
同一 ``job_id`` 运行中的 run 不杀，排队槽只留最新一次，旧排队项记
``superseded`` + ``not_sent``。

本模块只做控制面：worker 结束后追加 :class:`CronRun`（``receipts`` 为空
表示未决），不在这里注入 handoff。时钟由调用方传入，保持 C8 确定性。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from lca.contracts.models.cron.models import (
    CronJob,
    CronValidationError,
    ScheduledHandoff,
    TargetReceipt,
)
from lca.domain.cron.handoff_dispatch import ScheduledHandoffDispatcher
from lca.domain.cron.next_run import next_run
from lca.domain.cron.store import CronStore
from lca.domain.cron.worker_context import (
    CronWorkerResult,
    WorkerProductContext,
    assemble_worker_context,
)
from lca.infrastructure.scheduler_file_lock import (
    STALE_ABSOLUTE_CAP_S,
    SchedulerFileLock,
)

_log = logging.getLogger(__name__)

# ``agent`` 执行与 ``space_action`` 重试耗尽后的最长自然超时（ADR-0268 §7）。
_MAX_TIMEOUT_S = 86400

WorkerRunner = Callable[[str], Awaitable[CronWorkerResult]]
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
        handoff_dispatcher: ScheduledHandoffDispatcher | None = None,
    ) -> None:
        self._store = store
        self._file_lock = SchedulerFileLock(
            lock_dir, name="cron", default_interval_s=default_interval_s
        )
        self._workspace_path = workspace_path
        self._worker_runner = worker_runner
        self._default_interval_s = default_interval_s
        self._clock = clock if clock is not None else (lambda: datetime.now(UTC))
        self._handoff_dispatcher = handoff_dispatcher
        self._handoff_tasks: set[asyncio.Task[None]] = set()
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
            result = await self._execute_with_retries(job, run_id)
            self._store.append_run(
                job.id,
                outcome=result.outcome,
                receipts=result.receipts,
                finished_at=self._clock(),
                run_id=run_id,
            )
            self._maybe_start_handoff(job, run_id, result)
        except Exception:
            # 意外错误（如落盘失败）也不让 worker 任务带着异常结束。
            _log.exception("cron.worker_crashed job_id=%s run_id=%s", job.id, run_id)
            with contextlib.suppress(Exception):
                self._store.append_run(
                    job.id,
                    outcome="runtime_failure",
                    receipts=(),
                    finished_at=self._clock(),
                    run_id=run_id,
                )
        finally:
            self._active.pop(job.id, None)
            pending = self._pending.pop(job.id, None)
            if pending is not None:
                self._start_worker(job, pending)

    def _maybe_start_handoff(self, job: CronJob, run_id: str, result: CronWorkerResult) -> None:
        """起 handoff 轮，但不占住 worker 槽（ADR-0268 §6.1、§8.1）。

        worker 槽管的是这次到点的执行。handoff 轮是一次完整的 run，长度由它
        自己的预算决定，把它算进 worker 槽会让一个提醒占住排队位几分钟。
        """
        if self._handoff_dispatcher is None:
            return
        if job.execution.kind != "agent" or not job.delivery_targets:
            return
        if not result.worker_message:
            return
        task = asyncio.create_task(self._run_handoff(job, run_id, result))
        self._handoff_tasks.add(task)
        task.add_done_callback(self._handoff_tasks.discard)

    async def _run_handoff(self, job: CronJob, run_id: str, result: CronWorkerResult) -> None:
        dispatcher = self._handoff_dispatcher
        if dispatcher is None:
            return
        if result.outcome == "superseded":
            # §6: no parent turn, and the one CronRunOutcome member that
            # ScheduledHandoff rejects.
            return
        receipts: list[TargetReceipt] = []
        spawned: list[str] = []
        try:
            handoff = ScheduledHandoff(
                job_id=job.id,
                run_id=run_id,
                task_context=job,
                worker_message=result.worker_message,
                delivery_targets=job.delivery_targets,
                outcome=result.outcome,
            )
            for target in job.delivery_targets:
                try:
                    handoff_run_id = await dispatcher.dispatch(handoff, target=target)
                except Exception:
                    _log.exception(
                        "cron.handoff_dispatch_failed job_id=%s chat_id=%s",
                        job.id,
                        target.chat_id,
                    )
                    receipts.append(TargetReceipt(chat_id=target.chat_id, state="failed"))
                    continue
                spawned.append(handoff_run_id)
                # 身份先落盘，再等这一轮（ADR-0268 §6.1）。反过来会让崩溃之后
                # 的恢复把同一次到点再派一遍。
                with contextlib.suppress(Exception):
                    self._store.record_handoff_runs(job.id, run_id, tuple(spawned))
                try:
                    state = await dispatcher.await_receipt(handoff_run_id)
                except Exception:
                    _log.exception(
                        "cron.handoff_receipt_failed job_id=%s handoff_run_id=%s",
                        job.id,
                        handoff_run_id,
                    )
                    state = "failed"
                receipts.append(TargetReceipt(chat_id=target.chat_id, state=state))
        except Exception:
            _log.exception("cron.handoff_failed job_id=%s run_id=%s", job.id, run_id)
        if receipts:
            with contextlib.suppress(Exception):
                self._store.close_run_receipts(job.id, run_id, tuple(receipts))

    async def _execute_with_retries(self, job: CronJob, run_id: str) -> CronWorkerResult:
        """按 ``max_retries`` 重试 ``runtime_failure`` / ``timed_out``。

        重试使用同一个 ``run_id``（ADR-0268 §7）；``completed`` 立即返回。
        """
        text = assemble_worker_context(job.body, self._product_context(job, run_id))
        result = CronWorkerResult(outcome="runtime_failure")
        for attempt in range(job.max_retries + 1):
            result = await self._execute_once(job, run_id, text)
            if result.outcome == "completed":
                return result
            if attempt < job.max_retries:
                _log.warning(
                    "cron.worker_retry job_id=%s run_id=%s attempt=%d outcome=%s",
                    job.id,
                    run_id,
                    attempt + 1,
                    result.outcome,
                )
        return result

    async def _execute_once(self, job: CronJob, run_id: str, text: str) -> CronWorkerResult:
        """跑一次 worker；超时记 ``timed_out``，异常记 ``runtime_failure``。

        The worker's own result is authoritative on success. It carries one
        receipt per delivery target, which is the only record of whether the
        reminder reached anyone. Timing out or raising leaves no receipts, so
        ``CronRun.receipts`` stays empty and reads as undecided per
        ADR-0268 §6.
        """
        timeout = self._effective_timeout(job)
        try:
            if timeout is None:
                return await self._worker_runner(text)
            return await asyncio.wait_for(self._worker_runner(text), timeout=timeout)
        except TimeoutError:
            _log.warning(
                "cron.worker_timed_out job_id=%s run_id=%s timeout=%s",
                job.id,
                run_id,
                timeout,
            )
            return CronWorkerResult(outcome="timed_out")
        except Exception:
            _log.exception("cron.worker_runtime_failure job_id=%s run_id=%s", job.id, run_id)
            return CronWorkerResult(outcome="runtime_failure")

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
            outcome="superseded",
            receipts=(TargetReceipt(chat_id=None, state="not_sent"),),
            finished_at=now,
            run_id=run_id,
        )

    # ---- 文件锁（ADR-0263 §9①②）：实现见 SchedulerFileLock ----

    def _acquire_lock(self, now_ms: int) -> bool:
        return self._file_lock.acquire(now_ms)

    def release_lock(self) -> None:
        self._file_lock.release()


__all__ = [
    "STALE_ABSOLUTE_CAP_S",
    "CronScheduler",
    "CronTickReport",
]
