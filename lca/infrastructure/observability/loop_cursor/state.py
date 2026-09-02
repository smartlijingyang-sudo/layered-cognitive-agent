"""LoopCursor 内部状态(ADR-0169 D1 / D6)。

非 frozen — 内部可变字段;cursor 公共面 snapshot() 返回 frozen CursorSnapshot。
"""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.observability.loop_cursor import (
    CloseReason,
    IterationReason,
    PhaseName,
)


@dataclass
class _CursorState:
    run_id: str
    trace_id: str
    incarnation: int
    phase: PhaseName | None = None
    step_id: str | None = None
    step_index: int = 0
    iteration: int = 0
    attempt_in_step: int = 0
    iteration_reason: IterationReason | None = None
    stop_signal: CloseReason | None = None
    seq: int = 0
    closed: bool = False


__all__ = ["_CursorState"]
