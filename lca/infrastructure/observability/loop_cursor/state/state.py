"""LoopCursor 内部状态(ADR-0169 D1 / D6)。

非 frozen — 内部可变字段;cursor 公共面 snapshot() 返回 frozen CursorSnapshot。
incarnation 字段类型为 ``Incarnation``(frozen dataclass);plan_ref 与 seq
经由 Incarnation 暴露,snapshot 派生时取 ``incarnation_seq``。
"""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.observability.core.incarnation import Incarnation
from lca.contracts.observability.cursor.loop_cursor import (
    CloseReason,
    IterationReason,
    PhaseName,
)


@dataclass
class _CursorState:
    run_id: str
    trace_id: str
    incarnation: Incarnation
    phase: PhaseName | None = None
    iteration: int = 0
    attempt_in_step: int = 0
    iteration_reason: IterationReason | None = None
    stop_signal: CloseReason | None = None
    seq: int = 0
    halted: bool = False


__all__ = ["_CursorState"]
