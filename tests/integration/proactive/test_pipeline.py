"""主动消息完整链集成测试：调度 tick → 裁决 → 投递 → session 可读回。

用真实 SessionStore + 真实 ProactiveScheduler（文件锁/state 落 tmp），
不 mock 关键链路（decide/deliver/session.append 全是真实调用）。

投递目标 session 一律由测试预注册：生产中 session 由 run 绑定创建、终结时
dispose，deliverer 在 store miss 时不再伪造会话，miss 即 ``delivered=False``。
"""

import json
import logging
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from lca.cognition.proactive import decide  # noqa: F401  (链路完整性：gate 真实参与)
from lca.contracts.models.proactive import (
    DeliveryTarget,
    DeliveryTargetKind,
    ProactiveJob,
    ProactiveSource,
)
from lca.contracts.models.proactive.policy import ProactivePolicy
from lca.infrastructure.proactive import ProactiveDeliverer, ProactiveScheduler
from lca.plugins.session.runtime.store.store import SessionStore


def _make_scheduler(
    tmp: Path, jobs: list[ProactiveJob], policy: ProactivePolicy | None = None
) -> tuple[ProactiveScheduler, SessionStore]:
    store = SessionStore()
    deliverer = ProactiveDeliverer(store, state_dir=tmp / "state")
    sched = ProactiveScheduler(
        lock_dir=tmp / "locks",
        state_dir=tmp / "state",
        job_source=lambda: jobs,
        deliverer=deliverer,
        default_interval_s=60,
        policy=policy,
    )
    return sched, store


def _job(job_id, session_id, content="x", **kw):
    base = {
        "id": job_id,
        "interval_seconds": 60,
        "content": content,
        "target": DeliveryTarget(kind=DeliveryTargetKind.SESSION_APPEND, session_id=session_id),
        "requested": True,
    }
    base.update(kw)
    return ProactiveJob(**base)


def test_tick_delivers_due_job_to_session():
    tmp = Path(tempfile.mkdtemp())
    sched, store = _make_scheduler(tmp, [_job("job1", "sess-1", content="该喝水了")])
    store.create("sess-1")
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


def test_crash_between_deliver_and_state_save_does_not_duplicate():
    """deliver 成功、state 落盘前崩溃 → 重跑同一 firing 不重复投递。

    message id 取名义触发时刻而非 tick 执行时刻：state 未推进时两次
    _run_job 产出同一 id，deliverer 的 (session_id, proactive_id) 去重兜住。
    """
    tmp = Path(tempfile.mkdtemp())
    store = SessionStore()
    store.create("sess-crash")
    deliverer = ProactiveDeliverer(store, state_dir=tmp / "state")
    sched = ProactiveScheduler(
        lock_dir=tmp / "locks",
        state_dir=tmp / "state",
        job_source=lambda: [],
        deliverer=deliverer,
        default_interval_s=60,
    )
    job = _job("job-crash", "sess-crash", content="别重复")
    js: dict = {}  # 模拟崩溃：state 从未落盘，两次调用看到同一 js
    assert sched._run_job(job, js, now_ms=1_000_000) == "delivered"
    # 更晚的 tick 重跑同一 firing（state 仍未推进）
    assert sched._run_job(job, js, now_ms=9_999_999) == "delivered"
    session = store.get("sess-crash")
    assert session is not None
    events = [e for e in session._log if e.type == "surface/assistant_message"]
    assert len(events) == 1


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
    store.create("sess-2")
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
    job = _job("job3", "sess-3")
    sched1, _ = _make_scheduler(tmp, [job])
    sched2, store2 = _make_scheduler(tmp, [job])
    store2.create("sess-3")
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
    tmp = Path(tempfile.mkdtemp())
    job = _job("job4", "sess-4")
    sched, store = _make_scheduler(tmp, [job])
    store.create("sess-4")
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
    job = _job("job5", "sess-5")
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


def test_due_job_without_target_session_counts_as_failed():
    """到期任务的目标 session 不存在 → 计入 failed，绝不计入 delivered。

    deliver 对 store miss 不抛错，只回 ``delivered=False,
    reason=session_not_found``；scheduler 若把「没抛错」当成投递成功，
    job 状态就在为一条从未送达的消息背书。
    """
    tmp = Path(tempfile.mkdtemp())
    job = _job("job-orphan", "sess-gone")
    sched, store = _make_scheduler(tmp, [job])
    try:
        report = sched.tick(now_ms=1_000_000)
        assert report.jobs_due == 1
        assert report.delivered == 0
        assert report.failed == 1
        # 没伪造会话，也没有任何事件落地
        assert store.list() == ()
        state = json.loads((tmp / "state" / "state.json").read_text(encoding="utf-8"))
        assert state["job-orphan"]["last_error"] == "session_not_found"
    finally:
        sched.release_lock()


def test_response_carried_does_not_touch_session():
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


# ---------------- T2 / T4（ADR-0264 §5） ----------------


def test_credential_job_rejected_warns_no_session_residue(caplog):
    """T2：含凭证消息整条拒绝 + warning 事件可查，session 无残留。"""
    tmp = Path(tempfile.mkdtemp())
    job = _job("job-cred", "sess-cred", content="your api_key: sk-live-abcdef123456")
    sched, store = _make_scheduler(tmp, [job])
    try:
        with caplog.at_level(
            logging.WARNING, logger="lca.infrastructure.proactive.scheduler"
        ):
            report = sched.tick(now_ms=1_000_000)
        assert report.rejected == 1
        assert report.delivered == 0
        assert "proactive.rejected" in caplog.text
        # 无残留：REJECTED 路径根本不创建 session
        assert store.get("sess-cred") is None
    finally:
        sched.release_lock()


def test_disabled_policy_silent_no_session_event():
    """T4（政策层端到端）：enabled=False → SILENT，session 无新事件。"""
    tmp = Path(tempfile.mkdtemp())
    job = _job("job-q", "sess-q", content="该喝水了")
    sched, store = _make_scheduler(
        tmp, [job], policy=ProactivePolicy(enabled=False)
    )
    try:
        report = sched.tick(now_ms=1_000_000)
        assert report.silent == 1
        assert report.delivered == 0
        assert store.get("sess-q") is None
    finally:
        sched.release_lock()


def test_requested_with_verified_ref_delivers_chat(caplog):
    """requested + 合法 request_ref（job:<id> 背书）→ 必达。"""
    tmp = Path(tempfile.mkdtemp())
    job = ProactiveJob(
        id="job-req",
        interval_seconds=60,
        content="standing reminder",
        target=DeliveryTarget(
            kind=DeliveryTargetKind.SESSION_APPEND, session_id="sess-req"
        ),
        requested=True,
        request_ref="job:job-req",
    )
    sched, store = _make_scheduler(tmp, [job])
    store.create("sess-req")
    try:
        report = sched.tick(now_ms=1_000_000)
        assert report.delivered == 1
        session = store.get("sess-req")
        events = [e for e in session._log if e.type == "surface/assistant_message"]
        assert len(events) == 1
    finally:
        sched.release_lock()
