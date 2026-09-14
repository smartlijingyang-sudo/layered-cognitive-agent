"""ADR-0169 PR-1:InMemoryLoopCursor 测试替身行为。

2026-09-14 dead-code 修剪后只剩 ``advance`` + ``open_step`` + snapshot。
"""

from __future__ import annotations

import pytest

from lca.contracts.observability.core.incarnation import Incarnation
from lca.contracts.observability.cursor.loop_cursor import (
    CursorError,
    CursorSnapshot,
)
from lca.infrastructure.observability.loop_cursor import InMemoryLoopCursor


def _inc(seq: int = 1) -> Incarnation:
    return Incarnation(run_id="r1", plan_ref="plan-A", incarnation_seq=seq)


def test_in_memory_loop_cursor_satisfies_protocol() -> None:
    c = InMemoryLoopCursor(run_id="r1", trace_id="t1", incarnation=_inc(1))
    # 2026-09-14 修剪后只剩 snapshot + advance + open_step
    expected = {"snapshot", "advance", "open_step"}
    for name in expected:
        assert hasattr(c, name), f"InMemoryLoopCursor missing {name!r}"
    # 确认死代码不再暴露(避免悄悄加回)
    for removed in ("record_thinking", "record_tool_call",
                    "record_tool_result", "record_request_header",
                    "halt", "close", "fork"):
        assert not hasattr(c, removed), (
            f"{removed} 已从 LoopCursor Protocol 删除,实现层不该保留"
        )
    snap = c.snapshot
    assert isinstance(snap, CursorSnapshot)


def test_initial_snapshot_is_outside_loop() -> None:
    c = InMemoryLoopCursor(run_id="r1", trace_id="t1", incarnation=_inc(1))
    snap = c.snapshot
    assert snap.phase is None
    assert snap.iteration == 0
    assert snap.step_index == 0
    assert snap.attempt_in_step == 0
    assert snap.stop_signal is None
    assert snap.incarnation == 1


def test_advance_opens_phase_window() -> None:
    c = InMemoryLoopCursor(run_id="r1", trace_id="t1", incarnation=_inc(1))
    snap = c.advance("perceive")
    assert snap.phase == "perceive"


def test_open_step_advances_step_index_without_ep() -> None:
    """open_step 与 StdLoopCursor 同口径:L6 自增;无 spine 时不落 EP。"""
    c = InMemoryLoopCursor(run_id="r1", trace_id="t1", incarnation=_inc(1))
    c.advance("think")
    c.open_step("step-001")
    snap = c.snapshot
    assert snap.step_index == 1
    assert snap.step_id == "step-001"
    assert snap.attempt_in_step == 0


def test_open_step_idempotent_on_same_step_id() -> None:
    """open_step 幂等:同 step_id 在 step_open 仍为 True 时不再发第二条 EP。

    回归 run_c2d944661a78 / run_03cabc8d9559 — 重复 ``capture_pre_llm``
    不应让 cursor 重复 emit ``writable.step.start``。
    """
    spine_records: list[dict] = []

    class _RecordingSpine:
        def append(self, **kw: object) -> int:
            spine_records.append(dict(kw))
            return int(kw["seq"])  # type: ignore[arg-type]

    c = InMemoryLoopCursor(
        run_id="r1", trace_id="t1", incarnation=_inc(1), spine=_RecordingSpine()
    )
    c.advance("think")
    c.open_step("step-001")
    c.open_step("step-001")
    ws_calls = [
        r for r in spine_records
        if r.get("execution_point") == "writable.step.start"
    ]
    assert len(ws_calls) == 1, (
        f"open_step 重复同 step_id 应幂等,实际发出 {len(ws_calls)} 条 writable.step.start"
    )


class _RecordingSpine:
    """最小 spine stub:记录 append 调用。"""

    def __init__(self) -> None:
        self.records: list[dict] = []

    def append(self, **kw: object) -> int:
        self.records.append(dict(kw))
        return int(kw["seq"])  # type: ignore[arg-type]


def test_spine_mode_open_step_emits_writable_step_start() -> None:
    """有 spine 时 ``open_step`` 落 ``writable.step.start`` EP,与 StdLoopCursor 同口径。"""
    spine = _RecordingSpine()
    c = InMemoryLoopCursor(run_id="r1", trace_id="t1", incarnation=_inc(1), spine=spine)
    c.advance("think")
    c.open_step("step-001")
    eps = [r["execution_point"] for r in spine.records]
    assert eps == ["phase.think.fold", "writable.step.start"]
    assert spine.records[1]["payload"]["step_id"] == "step-001"


def test_advance_after_close_raises_cursor_error() -> None:
    """close 后 cursor 不可用;advance 必须 raise(CursorError 替身一致性)。"""
    # 关闭 cursor 的本意是「run 已结束,不再发 EP」。InMemoryLoopCursor 没有
    # close() 公共方法,改用「state.closed = True」直接模拟。
    c = InMemoryLoopCursor(run_id="r1", trace_id="t1", incarnation=_inc(1))
    c._state.closed = True
    with pytest.raises(CursorError):
        c.advance("perceive")
