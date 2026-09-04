"""StdLoopCursor — 默认实现(ADR-0169 D1 / D8)。

仅持 spine handle + _state;不持 deriver / projections / persistence /
llm hook / model_visible recorder 实例(评审 S1 处方,AST scan 验证)。
构造器签名只接 spine + identity(metadata);不接 host / persistence / capture。
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
from lca.contracts.observability.loop_cursor_payloads import (
    PhaseFoldPayload,
    RequestHeader,
    ThinkingRecord,
    ToolCallRecord,
    ToolResultRecord,
)
from lca.contracts.observability.resume import ResumeSpec
from lca.infrastructure.observability.loop_cursor._spine_port import WritePort
from lca.infrastructure.observability.loop_cursor.state import _CursorState


class StdLoopCursor:
    """默认 LoopCursor 实现 — 薄控制状态机(ADR-0169 P1 / D1)。

    状态转移合法性:
    - 进入 phase.X 后,record_X 必须在 X phase 窗口内调用
    - record_request_header 必在 THINK phase 调用,同时触发 step 自增
    - close() 之后所有 record_*/advance 抛 CursorError

    incarnation 显式身份(ADR-0169 D6 / L14):
    - cursor 持有 frozen Incarnation(run_id + plan_ref + incarnation_seq)
    - snapshot.incarnation 派生自 Incarnation.incarnation_seq
    - spine payload 携带 incarnation(plan_ref + seq),envelope 必携带(L14)
    """

    def __init__(
        self,
        *,
        spine: WritePort,
        run_id: str,
        trace_id: str,
        incarnation: Incarnation,
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
        """暴露当前 cursor 的显式身份(ADR-0169 D6);供 fork / Capture 读取。"""
        return self._state.incarnation

    @property
    def plan_ref(self) -> str:
        """Plan identity 顶层 accessor — ``cursor.plan_ref`` 等价于 ``cursor.incarnation.plan_ref``。

        ADR-0068 §决策二 + ADR-0169 D6:plan_ref 是 cursor 的显式身份之一
        (与 run_id / incarnation_seq 同级),reader 不必穿透 incarnation 字段
        就能拿到 16-hex plan ID。让 interpreter / fork / capture 都能直读,
        避免 ``getattr(cursor, "plan_ref", None)`` 这种 duck-type 谎言。

        与 :attr:`Incarnation.plan_ref` 同源(永远相等),只是 alias。
        """
        return self._state.incarnation.plan_ref

    # ── spine append helper ─────────────────────────────────────
    def _append(self, execution_point: str, payload: dict) -> int:
        s = self._state
        s.seq += 1
        return self._spine.append(
            execution_point=execution_point,
            payload=payload,
            run_id=s.run_id,
            seq=s.seq,
            incarnation=s.incarnation.incarnation_seq,
            phase=s.phase,
        )

    def _ensure_open(self) -> None:
        # close 优先(ADR-0169 D5):close 一律允许(halt→close 是合法转移,
        # 操作员放弃 resume 时释放资源);halted 仅锁住 record_* / advance。
        if self._state.closed:
            raise CursorError("cursor closed")

    def _ensure_not_halted(self) -> None:
        if self._state.halted:
            raise CursorError("cursor halted; awaiting resume")

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
    ) -> CursorSnapshot:
        """Phase 窗口转移,并唯一派生 ``phase.<name>.fold`` EP。

        强类型 payload(ADR-0169 P2 + SSOT 收口):
        - ``objective_kind`` 与 ``objective`` 必须配对 —— 不再接受裸 str,
          杜绝历史 bug(spine 同时出现 objective=模型名 与 objective=用户文本
          两条同 EP,因为 LLM adapter 把 ``objective=model`` 误传给 emit_phase)。
        - 不传 objective 时 objective_kind 默认为 ``system_role``,允许
          perceive / remember / stop 等不带 objective 的相位折叠。
        """
        self._ensure_open()
        self._ensure_not_halted()
        s = self._state
        # stop → perceive 触发新 iteration
        if s.phase == "stop" and phase == "perceive":
            s.iteration += 1
            s.attempt_in_step = 0
            s.step_index = 0
        elif s.phase == "stop" and phase != "perceive":
            raise CursorError(f"cannot advance from stop to {phase!r}")
        s.phase = phase
        # 派生 phase.<name>.fold EP(ADR-0169 P2 / L3)—— cursor 是唯一写入者
        fold_payload = PhaseFoldPayload(
            phase=phase,
            objective_kind=objective_kind,
            objective=objective,
            summary=summary,
        )
        self._append(
            execution_point=f"phase.{phase}.fold",
            payload={
                "phase": fold_payload.phase,
                "objective_kind": fold_payload.objective_kind,
                "objective": fold_payload.objective,
                "summary": fold_payload.summary,
                "incarnation": s.incarnation.incarnation_seq,
                "plan_ref": s.incarnation.plan_ref,
                "step_index": s.step_index,
            },
        )
        return self.snapshot

    def halt(self, reason: CloseReason) -> None:
        self._ensure_open()
        # ADR-0173 D1 halt != close:halt 仅锁住 record_* / advance,
        # 保留 cursor 实例等 spatial-temporal runtime 走 resume 协议重建。
        self._state.halted = True
        self._state.stop_signal = reason
        self._append(
            execution_point="writable.iteration.halt",
            payload={"reason": reason},
        )

    @staticmethod
    def resume_cursor(
        *,
        spine: WritePort,
        spec: ResumeSpec,
        trace_id: str,
    ) -> StdLoopCursor:
        """由 spatial-temporal runtime 调用:派生新 cursor 实例(I-RESUME-1)。

        新 cursor 复用 spine handle 与 spec 携带的 Incarnation;
        旧 halted cursor **不复用**,由 caller 负责析构。
        """
        incarnation = Incarnation(
            run_id=spec.run_id,
            plan_ref=spec.plan_ref,
            incarnation_seq=spec.incarnation_seq,
        )
        cursor = StdLoopCursor(
            spine=spine,
            run_id=spec.run_id,
            trace_id=trace_id,
            incarnation=incarnation,
        )
        # 注入 spec 携带的 snapshot 投影;新 cursor 默认 phase=None(OUTSIDE_LOOP),
        # caller 经由 advance(spec.phase) 开窗。
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
        # 发 closing 信号(CloseBarrier 协调 flush 顺序,ADR-0169 D5 / L16)
        self._append(
            execution_point="writable.iteration.closing",
            payload={"reason": reason},
        )

    # ── record_*(4)— cursor 注入 incarnation(ADR-0169 L14) ──────────
    def record_thinking(self, payload: ThinkingRecord, *, text_preview: str = "") -> None:
        """Emit ``step.thinking.record`` with an optional bounded text preview.

        Same forward-compat pattern as :meth:`record_tool_call`'s ``arguments``
        kwargs: the frozen :class:`ThinkingRecord` carries digest / path /
        token_count / kind, and callers may additionally attach
        ``text_preview`` (a short prefix of the thinking text) so step-tree
        readers can render the thinking without fetching the sidecar file.
        Non-empty ``text_preview`` is forwarded verbatim into the spine event
        payload; empty string is omitted from the payload.
        """
        self._ensure_open()
        self._ensure_not_halted()
        if self._state.phase != "think":
            raise CursorError("record_thinking must be in THINK window")
        event_payload: dict[str, object] = {
            "content_digest": payload.content_digest,
            "content_path": payload.content_path,
            "token_count": payload.token_count,
            "thinking_kind": payload.thinking_kind,
            "incarnation": self._state.incarnation.incarnation_seq,
            "plan_ref": self._state.incarnation.plan_ref,
            "step_index": self._state.step_index,
        }
        if text_preview:
            event_payload["text_preview"] = text_preview
        self._append(execution_point="step.thinking.record", payload=event_payload)

    def record_tool_call(
        self,
        payload: ToolCallRecord,
        *,
        arguments: dict[str, object] | None = None,
        arguments_summary: str = "",
        invocation_id: str = "",
    ) -> None:
        """Emit ``step.tool_call.record`` with rich arguments payload.

        The dataclass :class:`ToolCallRecord` carries only ``args_digest``
        + ``args_payload_path``. To make step-tree (and downstream
        readers) recoverable we accept ``arguments`` / ``arguments_summary``
        / ``invocation_id`` as keyword-only additions; when provided they
        are forwarded into the spine event payload so derivers do not
        have to fetch model_visible separately just to see what the
        tool was called with.
        """
        self._ensure_open()
        self._ensure_not_halted()
        if self._state.phase != "act":
            raise CursorError("record_tool_call must be in ACT window")
        event_payload: dict[str, object] = {
            "tool_name": payload.tool_name,
            "args_digest": payload.args_digest,
            "args_payload_path": payload.args_payload_path,
            "call_seq": payload.call_seq,
            "incarnation": self._state.incarnation.incarnation_seq,
            "plan_ref": self._state.incarnation.plan_ref,
            "step_index": self._state.step_index,
        }
        if arguments is not None:
            event_payload["arguments"] = arguments
        if arguments_summary:
            event_payload["arguments_summary"] = arguments_summary
        if invocation_id:
            event_payload["invocation_id"] = invocation_id
        self._append(execution_point="step.tool_call.record", payload=event_payload)

    def record_tool_result(
        self,
        payload: ToolResultRecord,
        *,
        invocation_id: str = "",
        ok: bool = True,
        latency_ms: int = 0,
        stdout_head: str = "",
        stdout_chars_total: int = 0,
        stdout_truncated: bool = False,
        stderr: str = "",
        files_created: tuple[str, ...] = (),
        error: str | None = None,
        delta_summary: str = "",
    ) -> None:
        """Emit ``step.tool_result.record`` with rich result fields.

        Same forward-compat pattern as :meth:`record_tool_call` —
        callers may attach the full result surface so step-tree readers
        do not have to round-trip through sidecars.
        """
        self._ensure_open()
        self._ensure_not_halted()
        if self._state.phase != "act":
            raise CursorError("record_tool_result must be in ACT window")
        event_payload: dict[str, object] = {
            "tool_name": payload.tool_name,
            "result_digest": payload.result_digest,
            "result_path": payload.result_path,
            "outcome": payload.outcome,
            "incarnation": self._state.incarnation.incarnation_seq,
            "plan_ref": self._state.incarnation.plan_ref,
            "step_index": self._state.step_index,
        }
        if invocation_id:
            event_payload["invocation_id"] = invocation_id
        if not ok:
            event_payload["ok"] = False
        if latency_ms:
            event_payload["latency_ms"] = latency_ms
        if stdout_head:
            event_payload["stdout_head"] = stdout_head
        if stdout_chars_total:
            event_payload["stdout_chars_total"] = stdout_chars_total
        if stdout_truncated:
            event_payload["stdout_truncated"] = True
        if stderr:
            event_payload["stderr"] = stderr
        if files_created:
            event_payload["files_created"] = list(files_created)
        if error is not None:
            event_payload["error"] = error
        if delta_summary:
            event_payload["delta_summary"] = delta_summary
        self._append(execution_point="step.tool_result.record", payload=event_payload)

    def record_request_header(self, header: RequestHeader) -> None:
        self._ensure_open()
        self._ensure_not_halted()
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
                "plan_ref": self._state.incarnation.plan_ref,
                "reason": header.reason,
                "model": header.model,
                # ADR-0185 spec §2.5 P5:system_digest / system_path 已
                # 合并到 messages_digest / messages_path(ADR-0176 D4),
                # 本写入只发 messages_* —— caller 从 messages_path 读
                # system 段。1 个 minor 版本兼容期后纯 messages_*。
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
        """派生 child cursor —— 共享 parent spine handle,递增 incarnation_seq。

        ADR-0171 I-FORK-1 / D1 / D6:
            - child 持有 parent 的 spine(共享 SSOT,L10)
            - child 不持独立 host / persistence / capture 实例
            - Incarnation 继承 parent.run_id + parent.plan_ref
            - incarnation_seq = parent.incarnation_seq + 1
            - child 的 iteration / step_index / attempt_in_step / seq 重新计数
            - 落 ``loop.fork`` EP,payload 携带 reason + child incarnation(ADR-0169 L14)
        """
        self._ensure_open()
        s = self._state
        # fork EP 携带 child incarnation(ADR-0171 D6,ADR-0169 L14)
        s.seq += 1
        self._spine.append(
            execution_point="loop.fork",
            payload={
                "reason": reason,
                "parent_incarnation": s.incarnation.incarnation_seq,
                "child_incarnation": s.incarnation.incarnation_seq + 1,
                "plan_ref": s.incarnation.plan_ref,
            },
            run_id=s.run_id,
            seq=s.seq,
            incarnation=s.incarnation.incarnation_seq,
            phase=s.phase,
        )
        return StdLoopCursor(
            spine=self._spine,
            run_id=s.run_id,
            trace_id=s.trace_id,
            incarnation=s.incarnation.child(),
        )


def _static_protocol_check() -> None:
    """编译期检查 StdLoopCursor 满足 LoopCursor Protocol。"""

    class _StubSpine:
        def append(self, **kw: object) -> int:
            return 0

    inc = Incarnation(run_id="r", plan_ref="p", incarnation_seq=1)
    _: LoopCursor = StdLoopCursor(
        spine=_StubSpine(),
        run_id="r",
        trace_id="t",
        incarnation=inc,
    )


__all__ = ["StdLoopCursor"]
