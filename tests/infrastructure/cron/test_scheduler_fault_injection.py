"""CronScheduler 故障注入测试（ADR-0268 §14.3，P3）。

覆盖：
- worker 被杀（mock worker 抛异常）→ 按 ``max_retries`` 重试，耗尽后 run
  记录 ``outcome = runtime_failure`` / ``timed_out``（handoff 的数据源）。
- 两个到点撞上运行中的 run → 旧排队项 ``outcome = superseded`` 且回执
  ``not_sent``；运行中的 worker 不被杀，排队项随后正常启动。
- 文件锁：stale 收割与持锁跳过。

测试用 mock 时钟、``tmp_path`` 作 assistant home、mock worker runner，
不启动真实 LLM。
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from lca.contracts.models.cron.models import (
    AgentExecution,
    ChatDelivery,
    CronJob,
    IntervalSchedule,
    OneShotSchedule,
    TargetReceipt,
)
from lca.domain.cron.store import CronStore
from lca.infrastructure.cron.scheduler import CronScheduler

_FIXED_CLOCK = datetime(2026, 10, 2, 9, 5, tzinfo=UTC)


def _job(**overrides: Any) -> CronJob:
    base: dict[str, Any] = {
        "id": "job_1",
        "title": "提醒",
        "schedule": OneShotSchedule(at=datetime(2026, 10, 1, 9, 0, tzinfo=UTC)),
        "timezone": "UTC",
        "body": "提醒我同步进度",
        "execution": AgentExecution(),
        "delivery_targets": (ChatDelivery(chat_id="chat_1"),),
        "report": "anomalies_only",
        "owner": "user_1",
        "created_chat_id": "chat_1",
        "anchor_at": datetime(2026, 10, 1, 9, 0, tzinfo=UTC),
        "enabled": True,
        "max_retries": 0,
        "timeout_seconds": None,
    }
    base.update(overrides)
    return CronJob(**base)


def _make_scheduler(
    tmp_path: Path,
    *,
    worker_runner: Any,
    store: CronStore | None = None,
    clock: Any = None,
) -> tuple[CronScheduler, CronStore]:
    store = store or CronStore(tmp_path)
    scheduler = CronScheduler(
        store=store,
        lock_dir=tmp_path / "lock",
        workspace_path=str(tmp_path),
        worker_runner=worker_runner,
        clock=clock or (lambda: _FIXED_CLOCK),
    )
    return scheduler, store


async def test_worker_failure_retries_then_records_runtime_failure(tmp_path: Path) -> None:
    """worker 抛异常：按 ``max_retries`` 重试，耗尽后记 ``runtime_failure``。"""
    store = CronStore(tmp_path)
    store.save_job(_job(max_retries=2))
    calls: list[str] = []

    async def failing_runner(text: str) -> str:
        calls.append(text)
        raise RuntimeError("boom")

    scheduler, _ = _make_scheduler(tmp_path, worker_runner=failing_runner, store=store)
    now = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)
    report = await scheduler.tick(now)
    await scheduler.wait_idle()

    assert report.due == 1
    assert report.started == 1
    # max_retries=2 → 共尝试 3 次。
    assert len(calls) == 3
    assert "job_id: job_1" in calls[0]
    runs = store.list_runs("job_1")
    assert len(runs) == 1
    assert runs[0].outcome == "runtime_failure"
    assert runs[0].receipts == ()
    assert runs[0].finished_at is not None


async def test_worker_timeout_records_timed_out(tmp_path: Path) -> None:
    """worker 超时：``asyncio.wait_for`` 杀掉任务，记 ``timed_out``。"""
    store = CronStore(tmp_path)
    store.save_job(_job(max_retries=0, timeout_seconds=1))

    async def slow_runner(text: str) -> str:
        del text
        await asyncio.sleep(60)
        return "done"

    scheduler, _ = _make_scheduler(tmp_path, worker_runner=slow_runner, store=store)
    now = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)
    await scheduler.tick(now)
    await scheduler.wait_idle()

    runs = store.list_runs("job_1")
    assert len(runs) == 1
    assert runs[0].outcome == "timed_out"
    assert runs[0].receipts == ()


async def test_worker_retries_then_succeeds(tmp_path: Path) -> None:
    """瞬时失败按 ``max_retries`` 重试后成功，记 ``completed``。"""
    store = CronStore(tmp_path)
    store.save_job(_job(max_retries=2))
    calls: list[str] = []

    async def flaky_runner(text: str) -> str:
        calls.append(text)
        if len(calls) < 3:
            raise RuntimeError("transient")
        return "ok"

    scheduler, _ = _make_scheduler(tmp_path, worker_runner=flaky_runner, store=store)
    now = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)
    await scheduler.tick(now)
    await scheduler.wait_idle()

    assert len(calls) == 3
    runs = store.list_runs("job_1")
    assert len(runs) == 1
    assert runs[0].outcome == "completed"
    assert runs[0].receipts == ()


async def test_due_while_running_queues_and_does_not_kill(tmp_path: Path) -> None:
    """运行中再撞到一个到点：不杀运行中的 worker，排队项随后启动。"""
    store = CronStore(tmp_path)
    anchor = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)
    store.save_job(_job(schedule=IntervalSchedule(every_seconds=60), anchor_at=anchor))
    release = asyncio.Event()
    finished: list[str] = []

    async def blocking_runner(text: str) -> str:
        await release.wait()
        finished.append(text)
        return "ok"

    scheduler, _ = _make_scheduler(tmp_path, worker_runner=blocking_runner, store=store)
    await scheduler.tick(anchor + timedelta(seconds=60))  # worker 1 启动并阻塞
    report = await scheduler.tick(anchor + timedelta(seconds=120))  # 入排队槽

    assert report.queued == 1
    assert report.started == 0  # 运行中不平行再起 worker
    # 运行中的 worker 没有 run 记录（未结束），排队项也没有落盘。
    assert store.list_runs("job_1") == []

    release.set()
    await scheduler.wait_idle()

    assert len(finished) == 2  # 运行中的 worker 正常结束 + 排队项随后启动
    runs = store.list_runs("job_1")
    assert all(run.outcome == "completed" for run in runs)
    assert len(runs) == 2


async def test_two_due_colliding_with_running_run_supersedes_older_pending(
    tmp_path: Path,
) -> None:
    """两个到点撞上运行中的 run：旧排队项 ``superseded`` + 回执 ``not_sent``。"""
    store = CronStore(tmp_path)
    anchor = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)
    store.save_job(_job(schedule=IntervalSchedule(every_seconds=60), anchor_at=anchor))
    release = asyncio.Event()

    async def blocking_runner(text: str) -> str:
        await release.wait()
        return "ok"

    scheduler, _ = _make_scheduler(tmp_path, worker_runner=blocking_runner, store=store)
    await scheduler.tick(anchor + timedelta(seconds=60))  # worker 1 启动
    await scheduler.tick(anchor + timedelta(seconds=120))  # 排队 run_2
    report = await scheduler.tick(anchor + timedelta(seconds=180))  # run_2 被取代

    assert report.superseded == 1
    runs = store.list_runs("job_1")
    superseded = [run for run in runs if run.outcome == "superseded"]
    assert len(superseded) == 1
    assert superseded[0].receipts == (TargetReceipt(chat_id=None, state="not_sent"),)

    # 运行中的 worker 不被杀：释放后运行中的 worker 与最新排队项都正常完成。
    release.set()
    await scheduler.wait_idle()

    by_outcome: dict[str, int] = {}
    for run in store.list_runs("job_1"):
        by_outcome[run.outcome] = by_outcome.get(run.outcome, 0) + 1
    assert by_outcome == {"completed": 2, "superseded": 1}


async def test_tick_skips_when_lock_held(tmp_path: Path) -> None:
    """锁未被抢占且未过期：tick 返回 ``lock_acquired=False``，不启动 worker。"""
    store = CronStore(tmp_path)
    store.save_job(_job())
    scheduler, _ = _make_scheduler(
        tmp_path,
        worker_runner=_never_called_runner,
        store=store,
    )
    now = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)
    lock_dir = tmp_path / "lock"
    lock_dir.mkdir(parents=True, exist_ok=True)
    now_ms = int(now.timestamp() * 1000)
    (lock_dir / "cron.lock").write_text(
        json.dumps({"owner": "other", "mtime_ms": now_ms}),
        encoding="utf-8",
    )

    report = await scheduler.tick(now)

    assert report.lock_acquired is False
    assert report.due == 0
    assert store.list_runs("job_1") == []


async def test_tick_reaps_stale_lock(tmp_path: Path) -> None:
    """锁持有者已崩溃（mtime 超过 stale 阈值）：收割后正常 tick。"""
    store = CronStore(tmp_path)
    store.save_job(_job(max_retries=0))
    scheduler, _ = _make_scheduler(
        tmp_path,
        worker_runner=_completed_runner,
        store=store,
    )
    now = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)
    lock_dir = tmp_path / "lock"
    lock_dir.mkdir(parents=True, exist_ok=True)
    stale_ms = int((now - timedelta(hours=2)).timestamp() * 1000)
    (lock_dir / "cron.lock").write_text(
        json.dumps({"owner": "crashed", "mtime_ms": stale_ms}),
        encoding="utf-8",
    )

    report = await scheduler.tick(now)
    await scheduler.wait_idle()

    assert report.lock_acquired is True
    assert report.started == 1
    runs = store.list_runs("job_1")
    assert len(runs) == 1
    assert runs[0].outcome == "completed"


async def _completed_runner(text: str) -> str:
    del text
    return "ok"


async def _never_called_runner(text: str) -> str:
    raise AssertionError("worker 不应在锁未取得时启动")
