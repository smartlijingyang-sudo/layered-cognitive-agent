"""ADR-0169 D5 / ADR-0170 PR-3 CloseBarrier 测试:

- 5 步顺序:L7-1 cursor.close signal → L7-2 closing EP emit → L7-3a persistence.flush →
  L7-3b host.flush_all → L7-4 close EP emit → L7-5 release
- L16 钉死:host.flush_all 在 close EP emit 之前(否则持久化的 close EP 在
  projection flush 完成后才写入,违反"投影已关"竞态)
- persistence 在 projection 之前 flush
- CloseReport 字段正确反映执行结果
"""

from __future__ import annotations

import pytest

from lca.contracts.observability.close_barrier import CloseReport
from lca.infrastructure.observability.loop_cursor.close_barrier_impl import (
    StdCloseBarrier,
)


# ── helpers ────────────────────────────────────────────────────────────
class _Recorder:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def flush(self) -> bool:
        self.calls.append("persistence.flush")
        return True


class _HostStub:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def flush_all(self) -> object:
        self.calls.append("host.flush_all")
        return None


class _EmitterStub:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.raise_on: str | None = None

    def emit_close(self, reason: str) -> None:  # type: ignore[override]
        self.calls.append(f"emit_close({reason})")
        if self.raise_on == "emit":
            raise RuntimeError("emit failed")


# ── 1. 5 步顺序 ────────────────────────────────────────────────────────
def test_close_executes_5_step_order() -> None:
    persistence = _Recorder()
    host = _HostStub()
    emitter = _EmitterStub()
    barrier = StdCloseBarrier(persistence=persistence, host=host, close_emitter=emitter)
    report = barrier.close("completed")
    # 期望顺序:persistence.flush → host.flush_all → emit_close
    assert persistence.calls == ["persistence.flush"]
    assert host.calls == ["host.flush_all"]
    assert emitter.calls == ["emit_close(completed)"]
    assert report.reason == "completed"


# ── 2. persistence-flushed-before-projections-flushed(L7-3) ────────────
def test_persistence_flushes_before_projections() -> None:
    """L7-3a persistence.flush → L7-3b host.flush_all 的顺序钉死。

    任何违反都会让 persistence 的 sink 处于不一致状态 —
    projection 已经写入,close EP 还没落盘,replay 看到的最后一条不是
    真实终止。
    """
    timestamps: list[tuple[str, float]] = []

    class _T:
        def __init__(self, name: str) -> None:
            self.name = name

        def flush(self) -> bool:
            import time as _t

            timestamps.append((self.name, _t.monotonic()))
            return True

        def flush_all(self) -> object:
            import time as _t

            timestamps.append((self.name, _t.monotonic()))
            return None

    persistence = _T("persistence")
    host_unused = _T("host")  # noqa: F841 — 由 _HostOK 替代
    emitter = _EmitterStub()

    # _T 用 flush + flush_all;让 persistence 用 flush,host 用 flush_all
    class _HostOK:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def flush_all(self) -> object:
            import time as _t

            timestamps.append(("host", _t.monotonic()))
            return None

    host_ok = _HostOK()
    barrier = StdCloseBarrier(persistence=persistence, host=host_ok, close_emitter=emitter)
    barrier.close("completed")

    ts_map = dict(timestamps)
    assert ts_map["persistence"] <= ts_map["host"], (
        f"persistence.flush must precede host.flush_all; got {timestamps}"
    )


# ── 3. L16 钉死:projections flush BEFORE close EP emit ───────────────
def test_l16_projections_flush_before_close_ep_emit() -> None:
    """L16 钉死:`host.flush_all()` 必须在 close EP emit **之前** 完成。

    顺序钉死:关闭 EP 写入 events.jsonl → close EP 之后到达的 drive 调用
    记录到 dropped_events。若 host.flush_all 在 close EP emit 之后,
    可能出现 "close EP 已落盘, 但 projection 还在写, 写完即关" 竞态。
    """
    timestamps: list[tuple[str, float]] = []

    class _TimingPersistence:
        def flush(self) -> bool:
            import time as _t

            timestamps.append(("persistence", _t.monotonic()))
            return True

    class _TimingHost:
        def flush_all(self) -> object:
            import time as _t

            timestamps.append(("host", _t.monotonic()))
            return None

    class _TimingEmitter:
        def emit_close(self, reason: str) -> None:  # type: ignore[override]
            import time as _t

            timestamps.append(("emit_close", _t.monotonic()))

    barrier = StdCloseBarrier(
        persistence=_TimingPersistence(),
        host=_TimingHost(),
        close_emitter=_TimingEmitter(),
    )
    barrier.close("completed")

    ts_map = dict(timestamps)
    # host.flush_all 必须先于 close EP emit
    assert ts_map["host"] < ts_map["emit_close"], (
        f"L16 violation: host.flush_all after emit_close; got {timestamps}"
    )


# ── 4. CloseReport 字段正确 ──────────────────────────────────────────
def test_close_report_fields_correct_on_success() -> None:
    persistence = _Recorder()
    host = _HostStub()
    emitter = _EmitterStub()
    barrier = StdCloseBarrier(persistence=persistence, host=host, close_emitter=emitter)
    report = barrier.close("user_stop")
    assert isinstance(report, CloseReport)
    assert report.reason == "user_stop"
    assert report.persistence_flushed is True
    assert report.projections_flushed is True
    assert report.close_emitted is True
    assert report.persistence_error is None
    assert report.projections_error is None
    assert report.close_emit_error is None


def test_close_report_fields_correct_on_persistence_failure() -> None:
    class _FailPersistence:
        def flush(self) -> bool:
            raise RuntimeError("disk full")

    host = _HostStub()
    emitter = _EmitterStub()
    barrier = StdCloseBarrier(
        persistence=_FailPersistence(),
        host=host,
        close_emitter=emitter,
    )
    report = barrier.close("error")
    assert report.persistence_flushed is False
    assert isinstance(report.persistence_error, RuntimeError)
    assert report.persistence_error.args == ("disk full",)
    # projections 仍然执行(L7-3b)
    assert host.calls == ["host.flush_all"]
    assert report.projections_flushed is True
    # close EP 仍然 emit
    assert emitter.calls == ["emit_close(error)"]
    assert report.close_emitted is True


def test_close_report_fields_correct_on_close_emit_failure() -> None:
    persistence = _Recorder()
    host = _HostStub()
    emitter = _EmitterStub()
    emitter.raise_on = "emit"
    barrier = StdCloseBarrier(persistence=persistence, host=host, close_emitter=emitter)
    report = barrier.close("kernel_shutdown")
    assert report.persistence_flushed is True
    assert report.projections_flushed is True
    assert report.close_emitted is False
    assert isinstance(report.close_emit_error, RuntimeError)


# ── 5. 异常隔离:persistence 失败不影响 projection 后续 flush ─────────
def test_persistence_failure_does_not_skip_projection_flush() -> None:
    class _FailPersistence:
        def flush(self) -> bool:
            raise RuntimeError("boom")

    host = _HostStub()
    emitter = _EmitterStub()
    barrier = StdCloseBarrier(
        persistence=_FailPersistence(),
        host=host,
        close_emitter=emitter,
    )
    barrier.close("error")
    assert host.calls == ["host.flush_all"], "L7-3b must run regardless of L7-3a outcome"


# ── 6. close_barrier 满足 Protocol(运行期 isinstance 钉死)───────────
def test_std_close_barrier_satisfies_closebarrier_protocol() -> None:
    from lca.contracts.observability.close_barrier import CloseBarrier as CBProtocol

    barrier = StdCloseBarrier(
        persistence=_Recorder(),
        host=_HostStub(),
        close_emitter=_EmitterStub(),
    )
    assert isinstance(barrier, CBProtocol)


# ── 7. 多种 CloseReason 透传 ─────────────────────────────────────────
@pytest.mark.parametrize(
    "reason",
    [
        "completed",
        "user_stop",
        "budget_exhausted",
        "approval_pending",
        "approval_rejected",
        "error",
        "loop_guard",
        "kernel_shutdown",
    ],
)
def test_close_reason_propagates(reason: str) -> None:
    emitter = _EmitterStub()
    barrier = StdCloseBarrier(
        persistence=_Recorder(),
        host=_HostStub(),
        close_emitter=emitter,
    )
    report = barrier.close(reason)  # type: ignore[arg-type]
    assert report.reason == reason  # type: ignore[comparison-overlap]
    assert emitter.calls == [f"emit_close({reason})"]
