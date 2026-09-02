"""CoordinatorAdapter —— StepCoordinator → LoopCursor 桥(ADR-0169 PR-21~25)。

背景
----
ADR-0169 §D11 PR-1 之后业务路径只允许两件事:``cursor.advance(phase)`` 与
``cursor.record_*(...)``。但 ``cognition/body/runtime/agent`` 仍有 10+ 调用方
使用 ``coord.begin_step / record_* / emit_phase / emit``(见 ADR-0169 §11
控制点迁移矩阵)。这些调用方在 PR-21~24 阶段逐一迁到 cursor;**在迁移完成
之前**,必须保证现有 ``coord.*`` API 仍可用,不能 break production。

职责
----
本适配器**不是新控制面**,而是把 ``StepCoordinator`` 旧 API 翻译成 cursor
新 API 的薄壳;cursor 是真值写入点(SSOT = spine),``StepCoordinator`` 仅
作为 compat 入口接收来自业务路径的调用,然后立即转发到 cursor。

设计要点
--------
- Adapter 持有一个 :class:`LoopCursor` 与一个 :class:`StepCoordinator`;
  所有 record_* 调用 **同时** 调 cursor + coord(双写),确保:
  - 现有 wiring(``get_current_coordinator`` / ContextVar)不破
  - cursor 是事实新增,projection / persistence 通过 spine 看到
- Adapter **不** 替代 StepCoordinator;Coord 的 begin_step / end_step / segment
  状态机仍由 StepCoordinator 持有(派生驱动 cursor 的 step_index)。
- ``coord.record_thinking / tool_call / tool_result`` 优先走 cursor;
  ``coord.begin_step / end_step / segment_* / emit_phase / emit`` 由
  StepCoordinator 内部派生 cursor.advance(phase)。
- 删除条件:grep ``coord.begin_step`` in ``lca/`` = 0 + grep
  ``coord.record_thinking`` in ``lca/`` = 0(ADR-0169 §D9,绑定 PR-21~24 后)。

COMPAT 块(AGENTS.md §1 + G15 模板)
-----------------------------------
# COMPAT(delete-when: PR-21~24 grep 全部为 0, tracking: ADR-0169-task-25)
# 兼容窗口:web-standard 业务迁移(PR-21~24)期间,coord.* 必须继续工作。
# 删除条件:``grep -rn "coord.begin_step|coord.record_thinking|coord.emit_phase" lca/cognition lca/body lca/runtime lca/agent`` 输出 0。
"""

from __future__ import annotations

from typing import Any

from lca.contracts.models.observability.journal_step import (
    ReflectTrace,
    SpanRecord,
    ThinkingTrace,
)
from lca.contracts.models.observability.journal_step import (
    ToolCallRecord as LegacyToolCallRecord,
)
from lca.contracts.models.observability.journal_step import (
    ToolResult as LegacyToolResult,
)
from lca.contracts.observability.loop_cursor import CloseReason, LoopCursor
from lca.contracts.observability.loop_cursor_payloads import (
    ThinkingRecord,
    ToolCallRecord,
    ToolResultRecord,
)
from lca.infrastructure.observability.writable_matrix.coordinator import StepCoordinator


# COMPAT(delete-when: PR-21~24 grep 全部为 0, tracking: ADR-0169-task-25)
class CoordinatorAdapter:
    """``StepCoordinator`` 的 LoopCursor 桥接器(ADR-0169 PR-25)。

    持有:
        cursor —— 新控制面(ADR-0169 D1,SSOT 写入)
        coord  —— 旧 StepCoordinator(只读 begin/end 状态机派生 cursor)

    行为:
        ``record_thinking(trace)`` →
            cursor.record_thinking(ThinkingRecord(...)) + coord.record_thinking(trace)
        ``record_tool_call(call)`` →
            cursor.record_tool_call(ToolCallRecord(...)) + coord.record_tool_call(call)
        ``record_tool_result(result)`` →
            cursor.record_tool_result(ToolResultRecord(...)) + coord.record_tool_result(result)
        ``begin_step(phase, **ctx)`` →
            coord.begin_step(phase, **ctx) → cursor.advance(phase)
        ``end_step(...)`` →
            coord.end_step(...) + cursor.advance('stop')(当 phase == 'act')
        ``emit_phase(phase, objective, summary, outcome)`` →
            cursor.advance(phase)(phase 派生 EP)
        ``emit(...)`` →
            coord.emit(...) 只走(不翻译,cursor 不暴露任意 EP 入口)

    业务代码在 PR-25 阶段仍直接用 ``StepCoordinator``;本适配器是为
    PR-21~24 业务迁移准备的过渡壳(由 wiring 层在切换时把 ``StepCoordinator``
    实例包成 ``CoordinatorAdapter``)。
    """

    def __init__(self, *, cursor: LoopCursor, coord: StepCoordinator) -> None:
        self._cursor = cursor
        self._coord = coord

    @property
    def cursor(self) -> LoopCursor:
        """暴露内部 cursor(PR-21~24 切换期供 wiring 层读取)。"""
        return self._cursor

    @property
    def coord(self) -> StepCoordinator:
        """暴露内部 coord(向后兼容;测试 / fixture 可读旧状态)。"""
        return self._coord

    # ── 切步:begin_step / end_step ─────────────────────────────────

    def begin_step(self, phase: str, **ctx: Any) -> str:
        """Step 开始 —— coord 派生 step_id, cursor 派生 phase 窗口。"""
        step_id = self._coord.begin_step(phase, **ctx)
        # 仅当 cursor 当前 phase != phase 时 advance(避免重复 EP)
        snap = self._cursor.snapshot
        if snap.phase != phase:  # type: ignore[comparison-overlap]
            self._cursor.advance(phase)  # type: ignore[arg-type]
        return step_id

    def end_step(
        self,
        outcome: str = "success",
        *,
        error: str | None = None,
    ) -> None:
        """Step 结束 —— coord 切走,cursor 转到 stop 候选(由调用方决定是否 advance)。"""
        self._coord.end_step(outcome, error=error)

    # ── phase 边(perceive/reflect/remember/stop 不开 step) ──────

    def emit_phase(
        self,
        *,
        phase: str,
        objective: str,
        summary: str,
        outcome: str = "ok",
    ) -> None:
        """``coord.emit_phase`` 翻译 → ``cursor.advance(phase)``。

        ``coord.emit_phase`` 写 ``phase.<name>.fold`` EP;cursor.advance(phase)
        也派生 ``phase.<name>.fold`` EP(ADR-0169 P2 / L3)。
        双写保 compat + 新增 SSOT 同步。
        """
        self._cursor.advance(phase)  # type: ignore[arg-type]
        self._coord.emit_phase(
            phase=phase,
            objective=objective,
            summary=summary,
            outcome=outcome,
        )

    # ── record_*: 同时调 cursor + coord(双写) ──────────────────

    def record_thinking(self, trace: ThinkingTrace) -> None:
        """``record_thinking`` 翻译 → ``cursor.record_thinking(ThinkingRecord(...))``。

        journal_step ``ThinkingTrace`` 字段 = model / latency_ms / reasoning /
        decision / tool_call / prompt_tokens / completion_tokens /
        raw_response_preview;cursor ``ThinkingRecord`` 字段 = content_digest /
        content_path / token_count / thinking_kind。映射:
            content_digest ← reasoning 字符串(由 spine-side digest 计算)
            content_path   ← None
            token_count    ← prompt_tokens + completion_tokens
            thinking_kind  ← "reasoning"
        """
        prompt_tokens = getattr(trace, "prompt_tokens", 0) or 0
        completion_tokens = getattr(trace, "completion_tokens", 0) or 0
        token_count = prompt_tokens + completion_tokens or None
        self._cursor.record_thinking(
            ThinkingRecord(
                content_digest=getattr(trace, "reasoning", ""),
                content_path=None,
                token_count=token_count,
                thinking_kind="reasoning",
            )
        )
        self._coord.record_thinking(trace)

    def record_tool_call(self, call: LegacyToolCallRecord) -> None:
        """``record_tool_call`` 翻译 → ``cursor.record_tool_call(ToolCallRecord(...))``。

        journal_step ``ToolCallRecord`` 字段 = invocation_id / name / arguments /
        arguments_summary;cursor ``ToolCallRecord`` 字段 = tool_name / args_digest /
        args_payload_path / call_seq。映射:
            tool_name       ← name
            args_digest     ← arguments_summary 或 invocation_id(降级)
            args_payload_path ← None(arguments 内容由 payload adapter 处理)
            call_seq        ← invocation_id 后缀 hash(去重来源)
        """
        tool_name = getattr(call, "name", "")
        args_digest = getattr(call, "arguments_summary", "") or getattr(call, "invocation_id", "")
        self._cursor.record_tool_call(
            ToolCallRecord(
                tool_name=tool_name,
                args_digest=args_digest,
                args_payload_path=None,
                call_seq=hash(getattr(call, "invocation_id", "")) & 0x7FFFFFFF,
            )
        )
        self._coord.record_tool_call(call)

    def record_tool_result(self, result: LegacyToolResult) -> None:
        """``record_tool_result`` 翻译 → ``cursor.record_tool_result(ToolResultRecord(...))``。

        journal_step ``ToolResult`` 没有 ``tool_name`` 字段(由 caller 上下文
        提供);cursor ``ToolResultRecord`` 必填 tool_name,降级用 ``delta_summary`` 或空串。
        """
        ok = bool(getattr(result, "ok", True))
        outcome: str = "ok" if ok else "failure"
        tool_name = getattr(result, "tool_name", "") or getattr(result, "delta_summary", "")
        self._cursor.record_tool_result(
            ToolResultRecord(
                tool_name=tool_name,
                result_digest=getattr(result, "delta_summary", ""),
                result_path=None,
                outcome=outcome,  # type: ignore[arg-type]
            )
        )
        self._coord.record_tool_result(result)

    def record_reflect(self, reflect: ReflectTrace) -> None:
        """``record_reflect`` —— cursor 无 record_reflect,仅 coord 写。"""
        # ADR-0169 D1:cursor 不暴露 record_reflect;reflect EP 由 spine subscribers 派生。
        self._coord.record_reflect(reflect)

    def record_span(self, span: SpanRecord) -> None:
        """``record_span`` —— cursor 无 record_span,仅 coord 写。"""
        self._coord.record_span(span)

    # ── 通用 emit —— cursor 不暴露,仅 coord 走 ──────────────────

    def emit(
        self,
        *,
        execution_point: str,
        channel: Any = "fact",
        payload: dict[str, Any] | None = None,
        outcome: Any = None,
        reason: str | None = None,
    ) -> None:
        """``coord.emit`` —— cursor 协议面**不**暴露任意 EP 入口;只走 coord。"""
        self._coord.emit(
            execution_point=execution_point,
            channel=channel,
            payload=payload,
            outcome=outcome,
            reason=reason,
        )

    # ── 关闭协同:close 透传到 cursor;CloseBarrier 由 runtime 持 ───

    def close(self, reason: CloseReason) -> None:
        """``adapter.close(reason)`` → ``cursor.close(reason)``。

        CloseBarrier 由 :class:`ObservabilityRuntime` 持有;本适配器不直接调用
        barrier,以保持 cursor 与 barrier 的解耦(ADR-0169 D5 / G6)。
        """
        self._cursor.close(reason)

    # ── context manager 便利 ─────────────────────────────────────

    def __enter__(self) -> CoordinatorAdapter:
        self._coord.__enter__()
        return self

    def __exit__(self, *exc: Any) -> None:
        self._coord.__exit__(*exc)

    # ── 透传属性(让外部仍能读 coord 上的字段) ─────────────────

    @property
    def run_id(self) -> str:
        return self._coord.run_id

    @property
    def trace_id(self) -> str:
        return self._coord.trace_id

    def __getattr__(self, name: str) -> Any:
        """未显式代理的方法 / 字段 —— 透传到 coord(向后兼容)。"""
        return getattr(self._coord, name)


__all__ = ["CoordinatorAdapter"]
