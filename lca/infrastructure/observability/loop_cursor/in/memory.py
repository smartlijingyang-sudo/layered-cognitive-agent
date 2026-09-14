"""In-memory LoopCursor — 测试替身(ADR-0169 L13)。

非法转移 raise CursorError;无 spine 写入;纯内存状态。
公共面与 :class:`StdLoopCursor` 对齐(2026-09-14 dead-code 修剪):
``record_*`` / ``halt`` / ``close`` / ``fork`` / ``resume_cursor`` 全删,
只留 ``advance`` + ``open_step`` + snapshot。
"""

from __future__ import annotations

from typing import Any, Literal

from lca.contracts.observability.core.incarnation import Incarnation
from lca.contracts.observability.cursor.loop_cursor import (
    CursorError,
    CursorSnapshot,
    LoopCursor,
    PhaseName,
)
from lca.infrastructure.observability.loop_cursor.state.state import _CursorState


class InMemoryLoopCursor:
    """纯内存 cursor;用于测试替身(ADR-0169 L13:null_loop_cursor 不存在)。"""

    def __init__(
        self,
        *,
        run_id: str,
        trace_id: str,
        incarnation: Incarnation,
        spine: Any = None,
    ) -> None:
        self._state = _CursorState(
            run_id=run_id,
            trace_id=trace_id,
            incarnation=incarnation,
        )
        # 可选 spine:有则 ``advance`` / ``open_step`` 派生 EP;无则纯内存状态机。
        self._spine = spine

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

    # ── 显式 step 边界(与 StdLoopCursor 同口径,ADR-0184 D6)────────
    def _emit_step_start(self, *, step_id: str) -> None:
        """有 spine 时发 ``writable.step.start``;无 spine 纯状态机则只置位。

        幂等:已开窗同 step_id 重复调用不发第二条 EP(与 StdLoopCursor 一致)。
        """
        s = self._state
        if s.step_open and s.step_id == step_id:
            return
        s.step_open = True
        s.step_id = step_id
        if self._spine is None:
            return
        s.seq += 1
        self._spine.append(
            execution_point="writable.step.start",
            payload={
                "step": s.step_index,
                "run_id": s.run_id,
                "step_id": step_id,
            },
            run_id=s.run_id,
            seq=s.seq,
            incarnation=s.incarnation.incarnation_seq,
            phase=s.phase,
        )

    def advance(
        self,
        phase: PhaseName,
        *,
        objective_kind: Literal[
            "user_text", "agent_role", "system_role", "model_name"
        ] = "system_role",
        objective: str = "",
        summary: str = "",
    ) -> CursorSnapshot:
        self._ensure_open()
        s = self._state
        if s.phase == "stop" and phase != "perceive":
            raise CursorError(f"cannot advance from stop to {phase!r}")
        if s.phase == "stop" and phase == "perceive":
            s.iteration += 1
            s.attempt_in_step = 0
            s.step_index = 0
        s.phase = phase
        if self._spine is not None:
            s.seq += 1
            self._spine.append(
                execution_point=f"phase.{phase}.fold",
                payload={
                    "phase": phase,
                    "objective_kind": objective_kind,
                    "objective": objective,
                    "summary": summary,
                    "incarnation": s.incarnation.incarnation_seq,
                    "plan_ref": s.incarnation.plan_ref,
                    "step_index": s.step_index,
                },
                run_id=s.run_id,
                seq=s.seq,
                incarnation=s.incarnation.incarnation_seq,
                phase=s.phase,
            )
        return self.snapshot

    def open_step(self, step_id: str) -> None:
        """LLM 边界 step 推进 —— L6 自增 + 显式 ``writable.step.start``。

        与 StdLoopCursor 同口径(ADR-0184 D6);``llm.request.header`` 仍由
        hook 侧唯一发射,本方法不派生。
        幂等:同 step_id 在 ``step_open`` 仍为 True 时不发第二条 EP。
        """
        self._ensure_open()
        s = self._state
        if s.step_open and s.step_id == step_id:
            return
        s.step_index += 1
        s.step_id = step_id
        s.attempt_in_step = 0
        self._emit_step_start(step_id=step_id)


def _static_protocol_check() -> None:
    """编译期检查 InMemoryLoopCursor 满足 LoopCursor Protocol(纯静态)。"""
    inc = Incarnation(run_id="r", plan_ref="p", incarnation_seq=1)
    _: LoopCursor = InMemoryLoopCursor(run_id="r", trace_id="t", incarnation=inc)


__all__ = ["InMemoryLoopCursor"]
