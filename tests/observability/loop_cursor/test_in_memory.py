"""ADR-0169 PR-1:InMemoryLoopCursor 测试替身行为。"""

from __future__ import annotations

import pytest

from lca.contracts.observability.incarnation import Incarnation
from lca.contracts.observability.loop_cursor import (
    CursorError,
    CursorSnapshot,
)
from lca.infrastructure.observability.loop_cursor import InMemoryLoopCursor


def _inc(seq: int = 1) -> Incarnation:
    return Incarnation(run_id="r1", plan_ref="plan-A", incarnation_seq=seq)


def test_in_memory_loop_cursor_satisfies_protocol() -> None:
    c = InMemoryLoopCursor(run_id="r1", trace_id="t1", incarnation=_inc(1))
    # 静态 duck-type 检查:9 个公共方法 + snapshot 属性
    expected = {
        "snapshot",
        "advance",
        "halt",
        "close",
        "record_thinking",
        "record_tool_call",
        "record_tool_result",
        "record_request_header",
        "fork",
    }
    for name in expected:
        assert hasattr(c, name), f"InMemoryLoopCursor missing {name!r}"
    # Protocol 字段类型(属性访问)
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


def test_close_after_close_raises_cursor_error() -> None:
    c = InMemoryLoopCursor(run_id="r1", trace_id="t1", incarnation=_inc(1))
    c.close("completed")
    with pytest.raises(CursorError):
        c.close("error")


def test_advance_after_close_raises_cursor_error() -> None:
    c = InMemoryLoopCursor(run_id="r1", trace_id="t1", incarnation=_inc(1))
    c.close("completed")
    with pytest.raises(CursorError):
        c.advance("perceive")


def test_record_thinking_outside_think_raises() -> None:
    c = InMemoryLoopCursor(run_id="r1", trace_id="t1", incarnation=_inc(1))
    c.advance("perceive")
    with pytest.raises(CursorError):
        c.record_thinking(None)  # type: ignore[arg-type]


def test_record_tool_call_outside_act_raises() -> None:
    c = InMemoryLoopCursor(run_id="r1", trace_id="t1", incarnation=_inc(1))
    c.advance("perceive")
    with pytest.raises(CursorError):
        c.record_tool_call(None)  # type: ignore[arg-type]


def test_record_request_header_must_open_think() -> None:
    c = InMemoryLoopCursor(run_id="r1", trace_id="t1", incarnation=_inc(1))
    c.advance("perceive")
    with pytest.raises(CursorError):
        c.record_request_header(None)  # type: ignore[arg-type]


def test_halt_sets_stop_signal() -> None:
    c = InMemoryLoopCursor(run_id="r1", trace_id="t1", incarnation=_inc(1))
    c.halt("user_stop")
    assert c.snapshot.stop_signal == "user_stop"


def test_fork_produces_independent_child() -> None:
    c = InMemoryLoopCursor(run_id="r1", trace_id="t1", incarnation=_inc(1))
    child = c.fork("child_agent")
    assert isinstance(child, InMemoryLoopCursor)
    # child 继承 identity + seq += 1(ADR-0171 P4)
    assert child.snapshot.incarnation == 2
    # 子 cursor 独立(初始 phase=None)
    assert child.snapshot.phase is None
