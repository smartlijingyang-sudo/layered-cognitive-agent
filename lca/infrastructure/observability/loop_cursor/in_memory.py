"""In-memory LoopCursor — 测试替身(ADR-0169 L13)。

非法转移 raise CursorError;无 spine 写入;纯内存状态。
"""

from __future__ import annotations

from typing import Literal

from lca.contracts.observability.incarnation import Incarnation
from lca.contracts.observability.loop_cursor import (
    CloseReason,
    CursorError,
    CursorSnapshot,
    LoopCursor,
    PhaseName,
)
from lca.infrastructure.observability.loop_cursor.state import _CursorState


class InMemoryLoopCursor:
    """纯内存 cursor;用于测试替身(ADR-0169 L13:NullLoopCursor 不存在)。"""

    def __init__(
        self,
        *,
        run_id: str,
        trace_id: str,
        incarnation: Incarnation,
    ) -> None:
        self._state = _CursorState(
            run_id=run_id,
            trace_id=trace_id,
            incarnation=incarnation,
        )

    @property
    def snapshot(self) -> CursorSnapshot:
        s = self._state
        return CursorSnapshot(
            run_id=s.run_id,
            trace_id=s.trace_id,
            incarnation=s.incarnation.incarnation_seq,
            step_id=s.step_id,
            step_index=s.step_index,
            iteration=s.iteration,
            attempt_in_step=s.attempt_in_step,
            phase=s.phase,
            iteration_reason=s.iteration_reason,
            stop_signal=s.stop_signal,
            seq=s.seq,
        )

    @property
    def incarnation(self) -> Incarnation:
        """暴露当前 cursor 的显式身份(ADR-0169 D6)。"""
        return self._state.incarnation

    def _ensure_open(self) -> None:
        if self._state.closed:
            raise CursorError("cursor closed")

    def advance(self, phase: PhaseName) -> CursorSnapshot:
        self._ensure_open()
        s = self._state
        # 进入 stop 之后必须 close 才能 advance
        if s.phase == "stop" and phase != "perceive":
            raise CursorError(f"cannot advance from stop to {phase!r}")
        # 业务：从 stop → perceive 触发新一轮 iteration
        if s.phase == "stop" and phase == "perceive":
            s.iteration += 1
            s.attempt_in_step = 0
            s.step_index = 0
        s.phase = phase
        # THINK / ACT 是 phase window "开窗"点 — 业务 record_* 在这两个 phase 才能调用
        return self.snapshot

    def halt(self, reason: CloseReason) -> None:
        self._ensure_open()
        self._state.stop_signal = reason

    def close(self, reason: CloseReason) -> None:
        self._ensure_open()
        s = self._state
        s.closed = True
        s.stop_signal = reason
        s.phase = None

    # ── record_*:在正确 phase window 才能调(L5 / L6) ──────────
    def record_thinking(self, payload: object) -> None:
        self._ensure_open()
        if self._state.phase != "think":
            raise CursorError("record_thinking must be in THINK window")

    def record_tool_call(self, payload: object) -> None:
        self._ensure_open()
        if self._state.phase != "act":
            raise CursorError("record_tool_call must be in ACT window")

    def record_tool_result(self, payload: object) -> None:
        self._ensure_open()
        if self._state.phase != "act":
            raise CursorError("record_tool_result must be in ACT window")

    def record_request_header(self, header: object) -> None:
        self._ensure_open()
        # L6 + D2 step 语义:record_request_header 必触发 think 开窗
        if self._state.phase != "think":
            raise CursorError("record_request_header must open THINK window")

    def fork(self, reason: Literal["child_agent", "delegation"]) -> LoopCursor:
        # ADR-0171:child 继承 parent Incarnation + seq += 1
        child_incarnation = self._state.incarnation.child()
        return InMemoryLoopCursor(
            run_id=self._state.run_id,
            trace_id=self._state.trace_id,
            incarnation=child_incarnation,
        )


def _static_protocol_check() -> None:
    """编译期检查 InMemoryLoopCursor 满足 LoopCursor Protocol(纯静态)。"""
    inc = Incarnation(run_id="r", plan_ref="p", incarnation_seq=1)
    _: LoopCursor = InMemoryLoopCursor(run_id="r", trace_id="t", incarnation=inc)


__all__ = ["InMemoryLoopCursor"]
