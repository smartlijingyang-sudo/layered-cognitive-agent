"""ADR-0263《例程调度互斥与自愈》验收契约测试（T5/C5：失败隔离与自愈）。

2026-10-03 实证：0263 T1–T4 已落地（main 含 locks.py /
verdicts.py / evaluate()，tests/contracts/routine/test_adr0263_acceptance.py
7 passed）；T5/C5 的验收主体 tick 驱动单元（ADR §10）源码侧零落地——
lca/application/routine/ 无 tick.py，生产无 tick 调用方（ADR §实证缺口④）。
本文件按 ADR T5 + §5 C5 + §9 决策记录③（重试 3 次、退避 1min/5min/15min、
3 次后死信保留 7 天）把验收标准钉成测试：当前全部预期红；quality lane
实现后转绿，不改测试。

tests lane 定义的契约 seam（quality lane 实现时遵循；开放设计点已标注）：
- lca.application.routine.tick.RoutineTickDriver(*, scheduler, repository,
lock_dir, stale_after_s=None, clock=time.time, on_event=None)
.tick_once(routines, executor) -> TickReport
.get_failure_state(routine_id) -> FailureState | None
.list_dead() -> list[DeadLetter]
executor: Callable[[RoutineSpec], None]。driver 按顺序处理 routines；
evaluate() 判定顺序沿用 T1–T4（enabled → 互斥锁 → SpendGuard → 时间窗口）。
- 常量（§9③）：RETRY_BACKOFFS_S = (60.0, 300.0, 900.0)；MAX_ATTEMPTS = 3；
DEAD_LETTER_TTL_S = 604800（7 天）。attempts=1 的失败用退避 index 0（60s），
attempts=2 用 index 1（300s）；attempts=3 的失败直接死信，不再退避。
- TickOutcome：EXECUTED / FAILED / SKIPPED / DEAD_LETTERED。
SKIPPED 的 skip_reason 复用 verdicts.SkipReason；退避窗口内的跳过记 NOT_DUE
（"还不到下一次尝试时间"——契约语义如此，不新增 verdicts 枚举）。
- FailureState（frozen）：routine_id / attempts / last_error /
last_failed_at_s / next_retry_at_s。失败计数必须持久化（repository
sidecar）：新 driver 实例同目录重建后仍可读——纯内存 dict 不算数。
- DeadLetter（frozen）：routine_id / attempts / last_error / dead_at_s /
expires_at_s；expires_at_s - dead_at_s == DEAD_LETTER_TTL_S。
- 失败事件留痕：on_event(event_name, payload) 回调；钉死事件名
"routine.failed.v1"（payload: routine_id / error / retry_count）与
"routine.dead_lettered.v1"（payload: routine_id / attempts / last_error）。
on_event 是开放设计点（生产接线 journal/spine 由 quality 定）；本测试只钉
driver 调用了它以及载荷字段齐全。
- 心跳刷新：RoutineFileLock 新增 refresh_heartbeat() -> None（把 heartbeat_ms
刷新为当前时间）。driver 在执行 executor 期间必须持有锁并刷新心跳，使长
持有不被 stale 收割误删——T5f 用"执行中并发 reclaim_stale() 返回 None"
钉死该保证。
- 开放设计点：失败计数 / dead-letter 的 repository 落盘形态（sidecar 文件名、
JSON schema）由 quality 定；本测试只经由 get_failure_state / list_dead 读，
不碰落盘格式。
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

try:
    from lca.application.routine.tick import (
        DEAD_LETTER_TTL_S,
        MAX_ATTEMPTS,
        RETRY_BACKOFFS_S,
        DeadLetter,
        FailureState,
        RoutineTickDriver,
        TickOutcome,
        TickReport,
        TickResult,
    )
except ImportError:  # ADR-0263 T5/C5 未落地：tick 驱动单元缺席
    DEAD_LETTER_TTL_S = None  # type: ignore[assignment]
    MAX_ATTEMPTS = None  # type: ignore[assignment]
    RETRY_BACKOFFS_S = None  # type: ignore[assignment]
    DeadLetter = None  # type: ignore[assignment]
    FailureState = None  # type: ignore[assignment]
    RoutineTickDriver = None  # type: ignore[assignment]
    TickOutcome = None  # type: ignore[assignment]
    TickReport = None  # type: ignore[assignment]
    TickResult = None  # type: ignore[assignment]

from lca.application.routine.locks import RoutineFileLock
from lca.application.routine.scheduler import RoutineSchedulerService
from lca.application.routine.spend_guard import SpendGuard
from lca.application.routine.verdicts import SkipReason
from lca.contracts.models.routine.models import RoutineSpec
from lca.domain.routine.repository import JsonRoutineRepository


def _require(name: str, sym):
    assert sym is not None, f"ADR-0263 T5/C5 未落地：{name} 缺席（预期红契约钉）"
    return sym


def _require_tick():
    _require("RETRY_BACKOFFS_S", RETRY_BACKOFFS_S)
    _require("MAX_ATTEMPTS", MAX_ATTEMPTS)
    _require("DEAD_LETTER_TTL_S", DEAD_LETTER_TTL_S)
    _require("lca.application.routine.tick.TickOutcome", TickOutcome)
    _require("lca.application.routine.tick.TickReport", TickReport)
    _require("lca.application.routine.tick.TickResult", TickResult)
    _require("lca.application.routine.tick.FailureState", FailureState)
    _require("lca.application.routine.tick.DeadLetter", DeadLetter)
    return _require("lca.application.routine.tick.RoutineTickDriver", RoutineTickDriver)


def _make_spec(routine_id: str = "rt_demo") -> RoutineSpec:
    return RoutineSpec(
        id=routine_id,
        name="demo routine",
        prompt="demo prompt",
        assistant_id="asst-1",
    )


def _make_driver(
    tmp_path: Path,
    specs: list[RoutineSpec] | None = None,
    *,
    clock=None,
    on_event=None,
    stale_after_s: float | None = None,
):
    driver_cls = _require_tick()
    repo_dir = tmp_path / "repo"
    lock_dir = tmp_path / "locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    repo = JsonRoutineRepository(repo_dir)
    guard = SpendGuard()
    for spec in specs or []:
        repo.save(spec)
    scheduler = RoutineSchedulerService(repository=repo, spend_guard=guard, lock_dir=lock_dir)
    driver = driver_cls(
        scheduler=scheduler,
        repository=repo,
        lock_dir=lock_dir,
        stale_after_s=stale_after_s,
        clock=clock or time.time,
        on_event=on_event,
    )
    return driver, repo, lock_dir


def _raising_executor(ran: list[str], fail_ids: set[str], error: str = "boom"):
    def executor(spec: RoutineSpec) -> None:
        ran.append(spec.id)
        if spec.id in fail_ids:
            raise RuntimeError(f"{error} happened in {spec.id}")

    return executor


class TestT5Constants:
    """§9③ 决策数字钉死：重试 3 次、退避 1min/5min/15min、死信保留 7 天。"""

    def test_backoff_schedule_and_limits(self):
        _require_tick()
        assert RETRY_BACKOFFS_S == (60.0, 300.0, 900.0)
        assert MAX_ATTEMPTS == 3
        assert DEAD_LETTER_TTL_S == 7 * 24 * 3600


class TestT5FailureIsolation:
    """T5：单个 routine 执行抛错，tick 继续处理下一个，无级联死亡。"""

    def test_single_failure_does_not_kill_tick(self, tmp_path):
        _require_tick()
        driver, _repo, _lock_dir = _make_driver(
            tmp_path, specs=[_make_spec("rt_boom"), _make_spec("rt_ok")]
        )
        ran: list[str] = []
        report = driver.tick_once(
            [_make_spec("rt_boom"), _make_spec("rt_ok")],
            _raising_executor(ran, {"rt_boom"}),
        )
        # tick_once 自身不抛：失败被隔离为结果
        by_id = {r.routine_id: r for r in report.results}
        assert by_id["rt_boom"].outcome == TickOutcome.FAILED
        assert by_id["rt_ok"].outcome == TickOutcome.EXECUTED
        assert ran == ["rt_boom", "rt_ok"]  # 失败后 tick 继续，不中断后续

    def test_failed_routine_leaves_no_stale_lock(self, tmp_path):
        _require_tick()
        driver, _repo, lock_dir = _make_driver(tmp_path, specs=[_make_spec("rt_boom")])
        ran: list[str] = []
        driver.tick_once([_make_spec("rt_boom")], _raising_executor(ran, {"rt_boom"}))
        # 失败后锁必须释放：下一 tick 不应被 ALREADY_RUNNING 卡死
        probe = RoutineFileLock(lock_dir=lock_dir, routine_id="rt_boom")
        assert probe.is_locked() is False


class TestT5RetryBackoff:
    """C5：失败计数进 repository；退避窗口内不重试，出窗口后重试。"""

    def test_failure_count_persisted_across_driver_instances(self, tmp_path):
        _require_tick()
        driver, _repo, _lock_dir = _make_driver(tmp_path, specs=[_make_spec("rt_boom")])
        ran: list[str] = []
        driver.tick_once([_make_spec("rt_boom")], _raising_executor(ran, {"rt_boom"}))
        state = driver.get_failure_state("rt_boom")
        assert state is not None
        assert state.attempts == 1
        assert "boom" in state.last_error
        # 新 driver 实例同目录重建：计数必须还在（持久化，非内存）
        driver2, _r2, _l2 = _make_driver(tmp_path, specs=[])
        state2 = driver2.get_failure_state("rt_boom")
        assert state2 is not None
        assert state2.attempts == 1
        assert state2.last_error == state.last_error

    def test_backoff_gates_retry_inside_window(self, tmp_path):
        _require_tick()
        now = [1_000_000.0]
        driver, _repo, _lock_dir = _make_driver(
            tmp_path, specs=[_make_spec("rt_boom")], clock=lambda: now[0]
        )
        ran: list[str] = []
        report = driver.tick_once([_make_spec("rt_boom")], _raising_executor(ran, {"rt_boom"}))
        assert report.results[0].outcome == TickOutcome.FAILED
        state = driver.get_failure_state("rt_boom")
        assert state.next_retry_at_s == now[0] + 60.0  # 退避 index 0 = 60s
        # 窗口内（+30s）：跳过，不执行
        now[0] += 30.0
        report2 = driver.tick_once([_make_spec("rt_boom")], _raising_executor(ran, {"rt_boom"}))
        assert report2.results[0].outcome == TickOutcome.SKIPPED
        assert report2.results[0].skip_reason == SkipReason.NOT_DUE
        assert ran == ["rt_boom"]  # executor 未被再次调用

    def test_retry_fires_after_backoff_with_longer_next_backoff(self, tmp_path):
        _require_tick()
        now = [1_000_000.0]
        driver, _repo, _lock_dir = _make_driver(
            tmp_path, specs=[_make_spec("rt_boom")], clock=lambda: now[0]
        )
        ran: list[str] = []
        driver.tick_once([_make_spec("rt_boom")], _raising_executor(ran, {"rt_boom"}))
        now[0] += 61.0  # 出 60s 窗口
        report = driver.tick_once([_make_spec("rt_boom")], _raising_executor(ran, {"rt_boom"}))
        assert report.results[0].outcome == TickOutcome.FAILED
        assert ran == ["rt_boom", "rt_boom"]  # 第 2 次执行发生
        state = driver.get_failure_state("rt_boom")
        assert state.attempts == 2
        assert state.next_retry_at_s == now[0] + 300.0  # 退避 index 1 = 300s

    def test_success_resets_failure_count(self, tmp_path):
        _require_tick()
        now = [1_000_000.0]
        driver, _repo, _lock_dir = _make_driver(
            tmp_path, specs=[_make_spec("rt_flaky")], clock=lambda: now[0]
        )
        ran: list[str] = []
        driver.tick_once([_make_spec("rt_flaky")], _raising_executor(ran, {"rt_flaky"}))
        assert driver.get_failure_state("rt_flaky").attempts == 1
        now[0] += 61.0
        report = driver.tick_once([_make_spec("rt_flaky")], _raising_executor(ran, set()))
        assert report.results[0].outcome == TickOutcome.EXECUTED
        assert driver.get_failure_state("rt_flaky") is None  # 成功清零


class TestT5DeadLetter:
    """C5：3 次失败后进死信，保留 7 天可查；死信后不再执行。"""

    def _fail_three_times(self, tmp_path, now):
        driver, _repo, _lock_dir = _make_driver(
            tmp_path, specs=[_make_spec("rt_doomed")], clock=lambda: now[0]
        )
        ran: list[str] = []
        for advance in (0.0, 61.0, 301.0):
            now[0] += advance
            driver.tick_once(
                [_make_spec("rt_doomed")],
                _raising_executor(ran, {"rt_doomed"}),
            )
        return driver, ran

    def test_three_failures_move_to_dead_letter(self, tmp_path):
        _require_tick()
        now = [2_000_000.0]
        driver, ran = self._fail_three_times(tmp_path, now)
        dead = driver.list_dead()
        assert len(dead) == 1
        entry = dead[0]
        assert entry.routine_id == "rt_doomed"
        assert entry.attempts == 3
        assert "boom" in entry.last_error
        assert entry.expires_at_s - entry.dead_at_s == 7 * 24 * 3600
        assert len(ran) == 3  # 恰好执行 3 次

    def test_dead_lettered_routine_not_executed_again(self, tmp_path):
        _require_tick()
        now = [2_000_000.0]
        driver, ran = self._fail_three_times(tmp_path, now)
        now[0] += 10_000.0  # 远超退避窗口
        report = driver.tick_once([_make_spec("rt_doomed")], _raising_executor(ran, {"rt_doomed"}))
        assert report.results[0].outcome == TickOutcome.DEAD_LETTERED
        assert len(ran) == 3  # 死信后不再执行


class TestT5EventTrace:
    """C5：失败事件留痕（含 routine_id / 错误摘要 / 已重试次数）。"""

    def test_failure_and_dead_letter_events_emitted(self, tmp_path):
        _require_tick()
        events: list[tuple[str, dict]] = []
        now = [3_000_000.0]
        driver, _repo, _lock_dir = _make_driver(
            tmp_path,
            specs=[_make_spec("rt_doomed")],
            clock=lambda: now[0],
            on_event=lambda name, payload: events.append((name, payload)),
        )
        ran: list[str] = []
        driver.tick_once([_make_spec("rt_doomed")], _raising_executor(ran, {"rt_doomed"}))
        failed_events = [p for n, p in events if n == "routine.failed.v1"]
        assert len(failed_events) == 1
        payload = failed_events[0]
        assert payload["routine_id"] == "rt_doomed"
        assert "boom" in payload["error"]
        assert payload["retry_count"] == 1
        # 再失败两次 → 死信事件
        for advance in (61.0, 301.0):
            now[0] += advance
            driver.tick_once(
                [_make_spec("rt_doomed")],
                _raising_executor(ran, {"rt_doomed"}),
            )
        dead_events = [p for n, p in events if n == "routine.dead_lettered.v1"]
        assert len(dead_events) == 1
        assert dead_events[0]["routine_id"] == "rt_doomed"
        assert dead_events[0]["attempts"] == 3
        assert "boom" in dead_events[0]["last_error"]


class TestT5HeartbeatRefresh:
    """C1/C2：执行期间 driver 持有锁并刷新心跳，长持有不被 stale 收割误删。"""

    def test_concurrent_reclaim_during_execution_returns_none(self, tmp_path):
        _require(
            "RoutineFileLock.refresh_heartbeat",
            getattr(RoutineFileLock, "refresh_heartbeat", None),
        )
        _require_tick()
        driver, _repo, lock_dir = _make_driver(
            tmp_path, specs=[_make_spec("rt_long")], stale_after_s=0.05
        )
        started = threading.Event()
        proceed = threading.Event()

        def executor(spec: RoutineSpec) -> None:
            started.set()
            assert proceed.wait(timeout=10)

        done: list = []

        def run_tick():
            done.append(driver.tick_once([_make_spec("rt_long")], executor))

        thread = threading.Thread(target=run_tick, daemon=True)
        thread.start()
        assert started.wait(timeout=10)
        rival = RoutineFileLock(lock_dir=lock_dir, routine_id="rt_long", stale_after_s=0.05)
        assert rival.is_locked() is True  # 执行中：锁确实被持有
        time.sleep(0.2)  # 4× stale 阈值：不刷新心跳必 stale
        assert rival.reclaim_stale() is None  # 心跳被刷新，未被收割
        proceed.set()
        thread.join(timeout=10)
        assert done[0].results[0].outcome == TickOutcome.EXECUTED
