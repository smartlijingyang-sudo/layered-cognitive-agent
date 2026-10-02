"""AvatarCostumeScheduler 测试（Task 8 / ADR-0269 §5）。

覆盖：avatar 任务筛选（artifact_id 过滤、停用跳过）、到期触发
``edit(auto_activate=True)`` 并追加 completed run、失败追加
``runtime_failure``、后台循环可停止。
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from lca.contracts.models.cron.models import (
    CronJob,
    DailySchedule,
    OneShotSchedule,
    SpaceActionExecution,
)
from lca.domain.cron.store import CronStore
from lca.plugins.avatar.scheduler import AvatarCostumeScheduler


def _job(job_id: str, body: str, enabled: bool = True) -> CronJob:
    now = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    return CronJob(
        id=job_id,
        title="avatar",
        schedule=DailySchedule(hour=12, minute=0),
        timezone="Asia/Shanghai",
        body=body,
        execution=SpaceActionExecution(artifact_id="avatar"),
        report="anomalies_only",
        owner="asst_1",
        created_chat_id="chat_1",
        anchor_at=now,
        enabled=enabled,
    )


def _due_oneshot_job(job_id: str, body: str) -> CronJob:
    """一次性任务且触发时刻已过：任何 ``now`` 下 ``next_run`` 都返回 due。"""
    return _job(job_id, body).model_copy(
        update={"schedule": OneShotSchedule(at=datetime(2026, 10, 1, 12, 0, tzinfo=UTC))}
    )


def test_scheduler_selects_avatar_jobs() -> None:
    jobs = [
        _job("j1", "雨天装扮"),
        _job("j2", "普通任务").model_copy(
            update={"execution": SpaceActionExecution(artifact_id="other")}
        ),
    ]
    selected = AvatarCostumeScheduler._select_avatar_jobs(jobs)
    assert [j.id for j in selected] == ["j1"]


def test_scheduler_disabled_job_skipped() -> None:
    jobs = [_job("j1", "x", enabled=False)]
    assert AvatarCostumeScheduler._select_avatar_jobs(jobs) == []


class _FakeAvatarService:
    def __init__(self, fail: bool = False) -> None:
        self.edits: list[tuple[str, str, bool]] = []
        self.fail = fail

    async def edit(
        self,
        assistant_id: str,
        user_request: str,
        reference_image: bytes | None = None,
        auto_activate: bool = False,
    ) -> object:
        del reference_image
        if self.fail:
            raise RuntimeError("edit failed")
        self.edits.append((assistant_id, user_request, auto_activate))
        return object()


async def test_due_job_triggers_edit_and_appends_completed_run(tmp_path: Path) -> None:
    store = CronStore(tmp_path)
    store.save_job(_due_oneshot_job("j1", "雨天装扮"))
    service = _FakeAvatarService()
    scheduler = AvatarCostumeScheduler(service=service, cron_store=store, tick_seconds=60)

    await scheduler._tick()

    assert service.edits == [("asst_1", "雨天装扮", True)]
    runs = store.get_run_records("j1")
    assert len(runs) == 1
    assert runs[0].outcome == "completed"
    assert runs[0].finished_at is not None


async def test_failed_edit_appends_runtime_failure(tmp_path: Path) -> None:
    store = CronStore(tmp_path)
    store.save_job(_due_oneshot_job("j1", "雨天装扮"))
    service = _FakeAvatarService(fail=True)
    scheduler = AvatarCostumeScheduler(service=service, cron_store=store, tick_seconds=60)

    await scheduler._tick()

    runs = store.get_run_records("j1")
    assert len(runs) == 1
    assert runs[0].outcome == "runtime_failure"
    assert runs[0].finished_at is not None


async def test_run_forever_can_be_stopped(tmp_path: Path) -> None:
    store = CronStore(tmp_path)
    scheduler = AvatarCostumeScheduler(
        service=_FakeAvatarService(), cron_store=store, tick_seconds=60
    )

    task = asyncio.create_task(scheduler.run_forever())
    scheduler.stop()
    await asyncio.wait_for(task, timeout=1)
    assert task.done()


def test_seconds_until_boundary_aligns_to_wall_clock() -> None:
    base = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    assert AvatarCostumeScheduler._seconds_until_boundary(base, tick_seconds=60) == 60.0

    fractional = datetime(2026, 10, 2, 12, 0, 0, 123456, tzinfo=UTC)
    assert AvatarCostumeScheduler._seconds_until_boundary(
        fractional, tick_seconds=60
    ) == pytest.approx(59.876544)

    mid = datetime(2026, 10, 2, 12, 0, 30, 500000, tzinfo=UTC)
    assert AvatarCostumeScheduler._seconds_until_boundary(mid, tick_seconds=60) == pytest.approx(
        29.5
    )

    # 对齐后的下一唤醒时刻落在秒边界上。
    aligned = fractional + timedelta(
        seconds=AvatarCostumeScheduler._seconds_until_boundary(fractional, 60)
    )
    assert aligned.second == 0
    assert aligned.microsecond == 0


async def test_daily_job_fires_after_second_boundary_alignment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import lca.plugins.avatar.scheduler as scheduler_mod

    real_datetime = scheduler_mod.datetime

    class _FakeDatetime(real_datetime):
        current = real_datetime(2026, 10, 2, 3, 59, 0, 123456, tzinfo=UTC)

        @classmethod
        def now(cls, tz=None):
            return cls.current

    monkeypatch.setattr(scheduler_mod, "datetime", _FakeDatetime)

    store = CronStore(tmp_path)
    # daily 12:00 Asia/Shanghai = 04:00 UTC；模拟相位偏移 .123456 的循环。
    store.save_job(_job("j1", "雨天装扮"))
    service = _FakeAvatarService()
    scheduler = AvatarCostumeScheduler(service=service, cron_store=store, tick_seconds=60)

    # 03:59:00.123456 UTC（上海 11:59:00.123456）：未到 12:00，不触发。
    await scheduler._tick()
    assert service.edits == []

    # 按边界对齐后下一次唤醒落在 04:00:00.000000 UTC（上海 12:00:00.000）。
    delay = scheduler._seconds_until_boundary(_FakeDatetime.current, 60)
    _FakeDatetime.current = _FakeDatetime.current + timedelta(seconds=delay)
    assert _FakeDatetime.current.second == 0
    assert _FakeDatetime.current.microsecond == 0

    # 边界时刻：daily 任务到期，触发换装。
    await scheduler._tick()
    assert service.edits == [("asst_1", "雨天装扮", True)]
