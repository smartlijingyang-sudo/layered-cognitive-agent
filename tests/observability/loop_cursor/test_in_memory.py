"""ADR-0169 PR-1:InMemoryLoopCursor 测试替身行为。

LoopCursor Protocol 钉死:``open_step`` 等第二轨方法禁止扩展,step 边界由
ModelVisibleHook 唯一驱动——实现层只剩 ``advance`` + snapshot。
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
    # Protocol 钉死只剩 snapshot + advance;open_step 属第二轨禁止扩展
    expected = {"snapshot", "advance"}
    for name in expected:
        assert hasattr(c, name), f"InMemoryLoopCursor missing {name!r}"
    # 确认死代码不再暴露(避免悄悄加回)
    for removed in (
        "record_thinking",
        "record_tool_call",
        "record_tool_result",
        "record_request_header",
        "halt",
        "close",
        "fork",
        "open_step",
        "begin_step",
        "end_step",
        "emit_step_start",
    ):
        assert not hasattr(c, removed), f"{removed} 已从 LoopCursor Protocol 删除,实现层不该保留"
    snap = c.snapshot
    assert isinstance(snap, CursorSnapshot)


def test_initial_snapshot_is_outside_loop() -> None:
    c = InMemoryLoopCursor(run_id="r1", trace_id="t1", incarnation=_inc(1))
    snap = c.snapshot
    assert snap.phase is None
    assert snap.iteration == 0
    assert snap.attempt_in_step == 0
    assert snap.stop_signal is None
    assert snap.incarnation == 1


def test_advance_opens_phase_window() -> None:
    c = InMemoryLoopCursor(run_id="r1", trace_id="t1", incarnation=_inc(1))
    snap = c.advance("perceive")
    assert snap.phase == "perceive"


def test_advance_after_stop_raises_cursor_error() -> None:
    """stop 后 cursor 不可用;advance 到非 perceive 必须 raise(CursorError)。"""
    # close() 已从公共面删除,收尾走 StdCloseBarrier;当前契约的等价守卫是
    # stop 窗口:stop -> perceive 是 resume,stop -> 其他 phase 非法。
    c = InMemoryLoopCursor(run_id="r1", trace_id="t1", incarnation=_inc(1))
    c.advance("stop")
    with pytest.raises(CursorError):
        c.advance("think")
