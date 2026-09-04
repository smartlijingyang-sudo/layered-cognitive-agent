"""LoopCursor 控制面 Protocol(ADR-0169 D1)。

业务路径唯一允许调用 advance / record_* / halt / close / fork / snapshot;
emit / subscribe / flush / close_storage / register_projection 全部不在公共面。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from lca.contracts.observability.loop_cursor_payloads import (
    RequestHeader,
    ThinkingRecord,
    ToolCallRecord,
    ToolResultRecord,
)

PhaseName = Literal[
    "perceive",
    "think",
    "gate",
    "act",
    "reflect",
    "remember",
    "stop",
]

CloseReason = Literal[
    "completed",
    "user_stop",
    "budget_exhausted",
    "approval_pending",
    "approval_rejected",
    "error",
    "loop_guard",
    "kernel_shutdown",
]

IterationReason = Literal[
    "tool_retry",
    "gate_retry",
    "checkpoint_resume",
    "subagent_resume",
    "user_replay",
]


@dataclass(frozen=True)
class CursorSnapshot:
    """只读视图;reducer / projection / persistence / observer 消费(ADR-0169 I-CURSOR-2)。

    字段语义钉死,新增必须先有 ADR:
    - phase=None ⇒ OUTSIDE_LOOP(cursor.close() 之前/之后)
    - step_index 自增,从 1 起;iteration 内重新计数
    - iteration ⊃ ADR-0095 iteration;attempt_in_step 与 iteration 独立计数
    """

    run_id: str
    trace_id: str
    incarnation: int
    step_id: str | None
    step_index: int
    iteration: int
    attempt_in_step: int
    phase: PhaseName | None
    iteration_reason: IterationReason | None
    stop_signal: CloseReason | None
    seq: int


class CursorError(Exception):
    """非法转移 / 关闭后调用 / 跨窗口 record → raise,不静默 fallback(ADR-0169 L13)。"""


class LoopCursor(Protocol):
    """Loop 控制面状态机。

    业务路径唯一允许做的:
        - advance(phase)            : 转移 phase 窗口;phase="stop" 时收口
                                      当前开窗的 step(落 writable.step.end,
                                      ADR-0184 D6)
        - halt(reason)              : 终止当前 iteration
        - close(reason)             : 关闭 cursor;未闭合 step 先落
                                      writable.step.end,再发 closing 信号
                                      给 CloseBarrier(ADR-0184 D6)
        - record_thinking(...)      : 落 step.thinking.record EP
        - record_tool_call(...)     : 落 step.tool_call.record EP
        - record_tool_result(...)   : 落 step.tool_result.record EP
        - record_request_header(...): 落 writable.step.start(显式 step 边界,
                                      先于 header)+ llm.request.header EP
                                      + 5 件套(ADR-0184 D6)
        - open_step(step_id)          : LLM 边界 step 自增 + 落
                                      writable.step.start;不落
                                      llm.request.header(该 EP 由 hook 侧
                                      Session 路径唯一发射,ADR-0185)
        - fork(reason) -> LoopCursor  : subagent / delegation
            (per ADR-0171:child cursor 共享 parent 的 spine handle,
             Incarnation 继承 run_id + plan_ref,incarnation_seq += 1;
             child 不持独立 host / persistence / capture 实例。)

    不暴露:
        begin_step / end_step / open_segment / close_segment
        emit_phase / emit / subscribe / flush / close_storage
        register_projection / subscribe_projection / drive_projection

    ``open_step`` 与 ``begin_step`` 的边界:前者做 L6 step_index 自增
    (状态机)+ 显式 ``writable.step.start`` 边界(ADR-0184 D6);
    ``begin_step`` 是 writable-matrix step 生命周期原语,仍不暴露。
    """

    @property
    def snapshot(self) -> CursorSnapshot: ...

    # ── 转移(3) ──────────────────────────────────────────────────
    def advance(
        self,
        phase: PhaseName,
        *,
        objective_kind: Literal[
            "user_text", "agent_role", "system_role", "model_name"
        ] = "system_role",
        objective: str = "",
        summary: str = "",
    ) -> CursorSnapshot: ...
    def halt(self, reason: CloseReason) -> None: ...
    def close(self, reason: CloseReason) -> None: ...

    # ── 事实记录(4) ──────────────────────────────────────────────
    def record_thinking(
        self,
        payload: ThinkingRecord,
        *,
        text_preview: str = "",
    ) -> None: ...
    def record_tool_call(self, payload: ToolCallRecord) -> None: ...
    def record_tool_result(self, payload: ToolResultRecord) -> None: ...

    # ── 横切(3) ──────────────────────────────────────────────────
    def record_request_header(self, header: RequestHeader) -> None: ...
    def open_step(self, step_id: str) -> None: ...
    def fork(self, reason: Literal["child_agent", "delegation"]) -> LoopCursor: ...


__all__ = [
    "CloseReason",
    "CursorError",
    "CursorSnapshot",
    "IterationReason",
    "LoopCursor",
    "PhaseName",
]
