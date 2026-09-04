"""LoopCursor 内部状态(ADR-0169 D1 / D6)。

非 frozen — 内部可变字段;cursor 公共面 snapshot() 返回 frozen CursorSnapshot。
incarnation 字段类型为 ``Incarnation``(frozen dataclass);plan_ref 与 seq
经由 Incarnation 暴露,snapshot 派生时取 ``incarnation_seq``。
"""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.observability.incarnation import Incarnation
from lca.contracts.observability.loop_cursor import (
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
    step_id: str | None = None
    step_index: int = 0
    iteration: int = 0
    attempt_in_step: int = 0
    iteration_reason: IterationReason | None = None
    stop_signal: CloseReason | None = None
    seq: int = 0
    closed: bool = False
    # ADR-0173 D1 halt != close:halt 保留 cursor 实例等待重建,
    # 但 record_* / advance 锁住(spatial-temporal runtime 持有 resume 协议)。
    halted: bool = False
    # ADR-0184 D6 显式 step 边界:有未闭合的 writable step 时为 True。
    # record_request_header / open_step 置 True(同点发 writable.step.start);
    # advance("stop") / close 消费(发 writable.step.end)后归 False,
    # 保证 end 不与 start 错配、不重复发射。
    step_open: bool = False


__all__ = ["_CursorState"]
