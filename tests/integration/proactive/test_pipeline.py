# -*- coding: utf-8 -*-
"""主动消息完整链集成测试：调度 tick → 裁决 → 投递 → session 可读回。

用真实 SessionStore + 真实 ProactiveScheduler（文件锁/state 落 tmp），
不 mock 关键链路（decide/deliver/session.append 全是真实调用）。
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/tmp/proactive-1")

from lca.cognition.proactive import decide  # noqa: F401  (链路完整性：gate 真实参与)
from lca.contracts.models.proactive import (
    DeliveryTarget,
    DeliveryTargetKind,
    ProactiveJob,
    ProactiveSource,
)
from lca.infrastructure.proactive import ProactiveDeliverer, ProactiveScheduler
from lca.plugins.session.runtime.store.store import SessionStore


def _make_scheduler(tmp: Path, jobs: list[ProactiveJob]) -> ProactiveScheduler:
    store = SessionStore()
    deliverer = ProactiveDeliverer(store)
    sched = ProactiveScheduler(
        lock_dir=tmp / "locks",
        state_dir=tmp / "state",
        job_source=lambda: jobs,
        deliverer=deliverer,
        default_interval_s=60,
    )
    return sched, store


def test_tick_delivers_due_job_to_session():
    tmp = Path(tempfile.mkdtemp())
    job = ProactiveJob(
        id="job1",
        interval_seconds=60,
        content="该喝水了",
        target=DeliveryTarget(
            kind=DeliveryTargetKind.SESSION_APPEND, session_id="sess-1"
        ),
        requested=True,
    )
    sched, store = _make_scheduler(tmp, [job])
    try:
        report = sched.tick(now_ms=1_000_000)
        assert report.lock_acquired is True
        assert report.jobs_due == 1
        assert report.delivered == 1
        session = store.get("sess-1")
        assert session is not None
        events = [e for e in session._log if e.type == "surface/assistant_message"]
        assert len(events) == 1
        assert events[0].data["content"] == "该喝水了"
        assert events[0].data["proactive"] is True
        assert events[0].data["turn"] == -1
    finally:
        sched.release_lock()


def test_tick_skips_not_due_job():
    tmp = Path(tempfile.mkdtemp())
    job = ProactiveJob(
        id="job2",
        interval_seconds=3600,
        content="not yet",
        target=DeliveryTarget(
            kind=DeliveryTargetKind.SESSION_APPEND, session_id="sess-2"
        ),
        requested=True,
    )
    sched, store = _make_scheduler(tmp, [job])
    try:
        # 第一次 tick 投递
        r1 = sched.tick(now_ms=1_000_000)
        assert r1.delivered == 1
        # 60 秒后：interval=3600，未到期
        r2 = sched.tick(now_ms=1_000_000 + 60_000)
        assert r2.jobs_due == 0
        assert r2.delivered == 0
        session = store.get("sess-2")
        assert len(session._log) == 1
    finally:
        sched.release_lock()


def test_lock_contention_second_tick_skipped():
    """两个调度器实例（模拟两个 carrier 进程）竞争：持有锁的一方未释放时，
    另一方 tick 拿不到锁直接跳过。"""
    tmp = Path(tempfile.mkdtemp())
    job = ProactiveJob(
        id="job3",
        interval_seconds=60,
        content="x",
        target=DeliveryTarget(
            kind=DeliveryTargetKind.SESSION_APPEND, session_id="sess-3"
        ),
        requested=True,
    )
    sched1, _ = _make_scheduler(tmp, [job])
    sched2, _ = _make_scheduler(tmp, [job])
    # sched1 模拟崩溃进程：只拿锁不走 tick（锁不释放）
    assert sched1._acquire_lock(1_000_000) is True
    try:
        r = sched2.tick(now_ms=1_000_000 + 1_000)
        assert r.lock_acquired is False
        assert r.jobs_due == 0
    finally:
        sched1.release_lock()
    # 锁释放后 sched2 可正常 tick
    r2 = sched2.tick(now_ms=1_000_000 + 2_000)
    assert r2.lock_acquired is True
    assert r2.delivered == 1


def test_stale_lock_reaped():
    import json

    tmp = Path(tempfile.mkdtemp())
    job = ProactiveJob(
        id="job4",
        interval_seconds=60,
        content="x",
        target=DeliveryTarget(
            kind=DeliveryTargetKind.SESSION_APPEND, session_id="sess-4"
        ),
        requested=True,
    )
    sched, store = _make_scheduler(tmp, [job])
    # 手工写入一个 stale 锁（模拟崩溃残留）：mtime=1_000_000，
    # tick 时刻已过 130s > stale 阈值（2×60s=120s）
    lock_file = tmp / "locks" / "proactive.lock"
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_file, "w", encoding="utf-8") as f:
        json.dump({"owner": "dead-host:1234", "mtime_ms": 1_000_000}, f)
    r = sched.tick(now_ms=1_000_000 + 130_000)
    assert r.lock_acquired is True  # stale 被收割
    assert r.delivered == 1


def test_failed_delivery_retries_then_dead_letters():
    tmp = Path(tempfile.mkdtemp())

    class BrokenStore:
        def get(self, session_id):
            raise RuntimeError("store exploded")

        def create(self, session_id=None):
            raise RuntimeError("store exploded")

    deliverer = ProactiveDeliverer(BrokenStore())
    job = ProactiveJob(
        id="job5",
        interval_seconds=60,
        content="x",
        target=DeliveryTarget(
            kind=DeliveryTargetKind.SESSION_APPEND, session_id="sess-5"
        ),
        requested=True,
    )
    sched = ProactiveScheduler(
        lock_dir=tmp / "locks",
        state_dir=tmp / "state",
        job_source=lambda: [job],
        deliverer=deliverer,
        default_interval_s=60,
    )
    try:
        t0 = 1_000_000
        # 第 1 次失败 → attempts=1, next_retry = t0+60s
        r1 = sched.tick(now_ms=t0)
        assert r1.failed == 1 and r1.dead_lettered == 0
        # 未到重试时间 → 跳过
        r2 = sched.tick(now_ms=t0 + 30_000)
        assert r2.jobs_due == 0
        # 第 2 次失败 → attempts=2, next_retry = +300s
        r3 = sched.tick(now_ms=t0 + 61_000)
        assert r3.failed == 1
        # 第 3 次失败 → 死信
        r4 = sched.tick(now_ms=t0 + 61_000 + 301_000)
        assert r4.dead_lettered == 1
        dead_files = list((tmp / "state" / "dead_letter").glob("*.json"))
        assert len(dead_files) == 1
    finally:
        sched.release_lock()


def test_response_carried_does_not_touch_session():
    tmp = Path(tempfile.mkdtemp())
    store = SessionStore()
    deliverer = ProactiveDeliverer(store)
    from lca.contracts.models.proactive import ProactiveMessage

    msg = ProactiveMessage(
        id="m-rc", content="欢迎", source=ProactiveSource.ONBOARDING_COMPLETED
    )
    target = DeliveryTarget(kind=DeliveryTargetKind.RESPONSE_CARRIED)
    receipt = deliverer.deliver(msg, target)
    assert receipt["delivered"] is True
    assert receipt["carried_message"]["content"] == "欢迎"
    assert store.list() == ()
