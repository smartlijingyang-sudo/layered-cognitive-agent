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
    CursorSnapshot,
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


def _snapshot_from_state(state: _CursorState) -> CursorSnapshot:
    """把内部 _CursorState 投影为 frozen CursorSnapshot(单处 canonical 实现)。

    InMemoryLoopCursor 与 StdLoopCursor 共用此投影;字段映射改一处即可,
    避免两处逐字相同实现漂移。internal seam,不进 __all__。
    """
    return CursorSnapshot(
        run_id=state.run_id,
        trace_id=state.trace_id,
        incarnation=state.incarnation.incarnation_seq,
        iteration=state.iteration,
        attempt_in_step=state.attempt_in_step,
        phase=state.phase,
        iteration_reason=state.iteration_reason,
        stop_signal=state.stop_signal,
        seq=state.seq,
    )


__all__ = ["_CursorState"]
