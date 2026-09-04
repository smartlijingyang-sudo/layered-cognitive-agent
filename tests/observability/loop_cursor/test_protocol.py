"""ADR-0169 PR-1:LoopCursor Protocol 公共面契约测试。"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from lca.contracts.observability.loop_cursor import (
    CloseReason,
    CursorError,
    CursorSnapshot,
    IterationReason,
    LoopCursor,
    PhaseName,
)


def test_phase_name_is_closed_set() -> None:
    assert set(PhaseName.__args__) == {
        "perceive",
        "think",
        "gate",
        "act",
        "reflect",
        "remember",
        "stop",
    }


def test_close_reason_is_closed_set() -> None:
    assert set(CloseReason.__args__) == {
        "completed",
        "user_stop",
        "budget_exhausted",
        "approval_pending",
        "approval_rejected",
        "error",
        "loop_guard",
        "kernel_shutdown",
    }


def test_iteration_reason_is_closed_set() -> None:
    assert set(IterationReason.__args__) == {
        "tool_retry",
        "gate_retry",
        "checkpoint_resume",
        "subagent_resume",
        "user_replay",
    }


def test_cursor_snapshot_is_frozen() -> None:
    s = CursorSnapshot(
        run_id="r1",
        trace_id="t1",
        incarnation=1,
        step_id=None,
        step_index=0,
        iteration=0,
        attempt_in_step=0,
        phase=None,
        iteration_reason=None,
        stop_signal=None,
        seq=0,
    )
    with pytest.raises(FrozenInstanceError):
        s.run_id = "r2"  # type: ignore[misc]


def test_cursor_error_is_exception_subclass() -> None:
    assert issubclass(CursorError, Exception)


def test_loop_cursor_protocol_has_10_methods() -> None:
    expected = {
        "advance",
        "halt",
        "close",
        "record_thinking",
        "record_tool_call",
        "record_tool_result",
        "record_request_header",
        "open_step",
        "fork",
        "snapshot",
    }
    assert expected <= set(dir(LoopCursor))
