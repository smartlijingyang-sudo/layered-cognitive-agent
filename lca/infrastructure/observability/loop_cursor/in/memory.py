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

    # ── step 计数器(SSOT=hook 端,本 cursor 不参与)──────────────
    # 历史:曾持有 step_index 自增;已砍掉,step 边界由 hook 唯一驱动。

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
        s = self._state
        if s.phase == "stop" and phase != "perceive":
            raise CursorError(f"cannot advance from stop to {phase!r}")
        if s.phase == "stop" and phase == "perceive":
            s.iteration += 1
            s.attempt_in_step = 0
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
                },
                run_id=s.run_id,
                seq=s.seq,
                incarnation=s.incarnation.incarnation_seq,
                phase=s.phase,
            )
        return self.snapshot


def _static_protocol_check() -> None:
    """编译期检查 InMemoryLoopCursor 满足 LoopCursor Protocol(纯静态)。"""
    inc = Incarnation(run_id="r", plan_ref="p", incarnation_seq=1)
    _: LoopCursor = InMemoryLoopCursor(run_id="r", trace_id="t", incarnation=inc)


__all__ = ["InMemoryLoopCursor"]
