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
from lca.contracts.observability.resume import ResumeSpec
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
        # close 一律允许(halt→close 是合法转移,操作员放弃 resume 时释放资源)
        if self._state.closed:
            raise CursorError("cursor closed")

    def _ensure_not_halted(self) -> None:
        if self._state.halted:
            raise CursorError("cursor halted; awaiting resume")

    def advance(self, phase: PhaseName) -> CursorSnapshot:
        self._ensure_open()
        self._ensure_not_halted()
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
        # ADR-0173 D1 halt != close:halt 仅锁住 record_* / advance,
        # 保留 cursor 实例等 spatial-temporal runtime 走 resume 协议重建。
        self._state.halted = True
        self._state.stop_signal = reason

    @staticmethod
    def resume_cursor(*, spec: ResumeSpec, trace_id: str) -> InMemoryLoopCursor:
        """测试替身:派生新 InMemoryLoopCursor 实例(I-RESUME-1)。"""
        incarnation = Incarnation(
            run_id=spec.run_id,
            plan_ref=spec.plan_ref,
            incarnation_seq=spec.incarnation_seq,
        )
        cursor = InMemoryLoopCursor(
            run_id=spec.run_id,
            trace_id=trace_id,
            incarnation=incarnation,
        )
        cursor._state.phase = spec.phase
        cursor._state.iteration = spec.iteration
        cursor._state.step_index = spec.step_index
        cursor._state.iteration_reason = spec.iteration_reason
        return cursor

    def close(self, reason: CloseReason) -> None:
        self._ensure_open()
        s = self._state
        s.closed = True
        s.stop_signal = reason
        s.phase = None

    # ── record_*:在正确 phase window 才能调(L5 / L6) ──────────
    def record_thinking(self, payload: object) -> None:
        self._ensure_open()
        self._ensure_not_halted()
        if self._state.phase != "think":
            raise CursorError("record_thinking must be in THINK window")

    def record_tool_call(self, payload: object) -> None:
        self._ensure_open()
        self._ensure_not_halted()
        if self._state.phase != "act":
            raise CursorError("record_tool_call must be in ACT window")

    def record_tool_result(self, payload: object) -> None:
        self._ensure_open()
        self._ensure_not_halted()
        if self._state.phase != "act":
            raise CursorError("record_tool_result must be in ACT window")

    def record_request_header(self, header: object) -> None:
        self._ensure_open()
        self._ensure_not_halted()
        # L6 + D2 step 语义:record_request_header 必触发 think 开窗
        if self._state.phase != "think":
            raise CursorError("record_request_header must open THINK window")

    def fork(self, reason: Literal["child_agent", "delegation"]) -> LoopCursor:
        """派生 child cursor —— Incarnation.child() 继承 run_id + plan_ref,seq += 1。

        ADR-0171 I-FORK-1 / D1:child 不持独立 host / persistence / capture;
        状态机自行重置(seq / step_index / iteration / attempt_in_step)。
        """
        self._ensure_open()
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
