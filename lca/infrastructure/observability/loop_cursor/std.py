"""StdLoopCursor — 默认实现(ADR-0169 D1 / D8)。

仅持 spine handle + _state;不持 deriver / projections / persistence /
llm hook / model_visible recorder 实例(评审 S1 处方,AST scan 验证)。
构造器签名只接 spine + identity(metadata);不接 host / persistence / capture。
"""

from __future__ import annotations

from typing import Literal

from lca.contracts.observability.loop_cursor import (
    CloseReason,
    CursorError,
    CursorSnapshot,
    LoopCursor,
    PhaseName,
)
from lca.contracts.observability.loop_cursor_payloads import (
    RequestHeader,
    ThinkingRecord,
    ToolCallRecord,
    ToolResultRecord,
)
from lca.infrastructure.observability.loop_cursor._spine_port import WritePort
from lca.infrastructure.observability.loop_cursor.state import _CursorState


class StdLoopCursor:
    """默认 LoopCursor 实现 — 薄控制状态机(ADR-0169 P1 / D1)。

    状态转移合法性:
    - 进入 phase.X 后,record_X 必须在 X phase 窗口内调用
    - record_request_header 必在 THINK phase 调用,同时触发 step 自增
    - close() 之后所有 record_*/advance 抛 CursorError
    """

    def __init__(
        self,
        *,
        spine: WritePort,
        run_id: str,
        trace_id: str,
        incarnation: int,
    ) -> None:
        self._spine = spine
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
            incarnation=s.incarnation,
            step_id=s.step_id,
            step_index=s.step_index,
            iteration=s.iteration,
            attempt_in_step=s.attempt_in_step,
            phase=s.phase,
            iteration_reason=s.iteration_reason,
            stop_signal=s.stop_signal,
            seq=s.seq,
        )

    # ── spine append helper ─────────────────────────────────────
    def _append(self, execution_point: str, payload: dict) -> int:
        s = self._state
        s.seq += 1
        return self._spine.append(
            execution_point=execution_point,
            payload=payload,
            run_id=s.run_id,
            seq=s.seq,
            incarnation=s.incarnation,
            phase=s.phase,
        )

    def _ensure_open(self) -> None:
        if self._state.closed:
            raise CursorError("cursor closed")

    # ── 转移(3) ──────────────────────────────────────────────────
    def advance(self, phase: PhaseName) -> CursorSnapshot:
        self._ensure_open()
        s = self._state
        # stop → perceive 触发新 iteration
        if s.phase == "stop" and phase == "perceive":
            s.iteration += 1
            s.attempt_in_step = 0
            s.step_index = 0
        elif s.phase == "stop" and phase != "perceive":
            raise CursorError(f"cannot advance from stop to {phase!r}")
        s.phase = phase
        # 派生 phase.<name>.fold EP(ADR-0169 P2 / L3)
        self._append(
            execution_point=f"phase.{phase}.fold",
            payload={"phase": phase},
        )
        return self.snapshot

    def halt(self, reason: CloseReason) -> None:
        self._ensure_open()
        self._state.stop_signal = reason
        self._append(
            execution_point="writable.iteration.halt",
            payload={"reason": reason},
        )

    def close(self, reason: CloseReason) -> None:
        self._ensure_open()
        s = self._state
        s.closed = True
        s.stop_signal = reason
        s.phase = None
        # 发 closing 信号(CloseBarrier 协调 flush 顺序,ADR-0169 D5 / L16)
        self._append(
            execution_point="writable.iteration.closing",
            payload={"reason": reason},
        )

    # ── record_*(4)— cursor 派生 step_id / incarnation / call_seq ──────────
    def record_thinking(self, payload: ThinkingRecord) -> None:
        self._ensure_open()
        if self._state.phase != "think":
            raise CursorError("record_thinking must be in THINK window")
        self._append(
            execution_point="step.thinking.record",
            payload={
                "content_digest": payload.content_digest,
                "content_path": payload.content_path,
                "token_count": payload.token_count,
                "thinking_kind": payload.thinking_kind,
                "incarnation": self._state.incarnation,
                "step_index": self._state.step_index,
            },
        )

    def record_tool_call(self, payload: ToolCallRecord) -> None:
        self._ensure_open()
        if self._state.phase != "act":
            raise CursorError("record_tool_call must be in ACT window")
        self._append(
            execution_point="step.tool_call.record",
            payload={
                "tool_name": payload.tool_name,
                "args_digest": payload.args_digest,
                "args_payload_path": payload.args_payload_path,
                "call_seq": payload.call_seq,
                "incarnation": self._state.incarnation,
                "step_index": self._state.step_index,
            },
        )

    def record_tool_result(self, payload: ToolResultRecord) -> None:
        self._ensure_open()
        if self._state.phase != "act":
            raise CursorError("record_tool_result must be in ACT window")
        self._append(
            execution_point="step.tool_result.record",
            payload={
                "tool_name": payload.tool_name,
                "result_digest": payload.result_digest,
                "result_path": payload.result_path,
                "outcome": payload.outcome,
                "incarnation": self._state.incarnation,
                "step_index": self._state.step_index,
            },
        )

    def record_request_header(self, header: RequestHeader) -> None:
        self._ensure_open()
        # L6 + D2 step 语义:record_request_header 必在 THINK phase 调用
        if self._state.phase != "think":
            raise CursorError("record_request_header must open THINK window")
        s = self._state
        s.step_index += 1
        s.step_id = header.step_id
        s.attempt_in_step = 0
        self._append(
            execution_point="llm.request.header",
            payload={
                "step_id": header.step_id,
                "incarnation": header.incarnation,
                "reason": header.reason,
                "model": header.model,
                "system_digest": header.system_digest,
                "system_path": header.system_path,
                "tools_digest": header.tools_digest,
                "tools_path": header.tools_path,
                "messages_digest": header.messages_digest,
                "messages_path": header.messages_path,
                "manifest_digest": header.manifest_digest,
                "manifest_path": header.manifest_path,
                "inherited_from_step": header.inherited_from_step,
            },
        )

    def fork(self, reason: Literal["child_agent", "delegation"]) -> LoopCursor:
        # ADR-0171 接管共享 Host 语义;本 PR 产出独立子 cursor
        return StdLoopCursor(
            spine=self._spine,
            run_id=self._state.run_id,
            trace_id=self._state.trace_id,
            incarnation=self._state.incarnation,
        )


def _static_protocol_check() -> None:
    """编译期检查 StdLoopCursor 满足 LoopCursor Protocol。"""

    class _StubSpine:
        def append(self, **kw: object) -> int:
            return 0

    _: LoopCursor = StdLoopCursor(
        spine=_StubSpine(),
        run_id="r",
        trace_id="t",
        incarnation=1,
    )


__all__ = ["StdLoopCursor"]
