"""LoopCursor 控制面 Protocol(ADR-0169 D1)。

业务路径唯一允许调用 ``advance`` / ``open_step``;其余 record_* /
halt / close / fork 全部不在公共面(2026-09-14 dead-code 修剪:这些方法
在生产路径零 caller,被删除)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

PhaseName = Literal[
    "perceive",
    "think",
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
    - phase=None ⇒ OUTSIDE_LOOP(cursor 关闭后)
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
        - advance(phase)        : 转移 phase 窗口;唯一派生
                                  ``phase.<name>.fold`` EP。
        - open_step(step_id)    : LLM 边界 step 自增 + 落
                                  ``writable.step.start`` EP(ADR-0184 D6)。
                                  ``llm.request.header`` 由 hook 侧
                                  Session 路径唯一发射(ADR-0185)。

    不暴露:
        ``record_thinking`` / ``record_tool_call`` / ``record_tool_result`` /
        ``record_request_header`` / ``halt`` / ``close`` / ``fork`` /
        ``resume_cursor`` / ``emit_phase`` / ``emit`` / ``subscribe`` /
        ``flush`` / ``begin_step`` / ``end_step`` / ``open_segment`` /
        ``close_segment`` / ``register_projection``。

    这些接口历史上属于 cursor 第二轨(``coord.*`` 路径),2026-09-14 修
    剪确认生产零 caller,留 Protocol 层禁止扩展。Runtime 收尾走
    :class:`~lca.infrastructure.observability.loop_cursor.close.barrier_impl.StdCloseBarrier`。
    """

    @property
    def snapshot(self) -> CursorSnapshot: ...

    # ── 转移(1) ──────────────────────────────────────────────────
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

    # ── LLM 边界 step 推进(1) ───────────────────────────────────
    def open_step(self, step_id: str) -> None: ...


__all__ = [
    "CloseReason",
    "CursorError",
    "CursorSnapshot",
    "IterationReason",
    "LoopCursor",
    "PhaseName",
]
