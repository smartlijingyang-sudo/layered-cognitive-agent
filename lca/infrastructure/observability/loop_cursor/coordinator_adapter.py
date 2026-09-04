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
  ``coord.begin_step / end_step / segment_*`` 由 StepCoordinator 内部派生
  cursor.advance(phase)。
- 删除条件:grep ``coord.begin_step`` in ``lca/`` = 0 + grep
  ``coord.record_thinking`` in ``lca/`` = 0(ADR-0169 §D9,绑定 PR-21~24 后)。

COMPAT 块(AGENTS.md §1 + G15 模板)
-----------------------------------
# COMPAT(delete-when: PR-21~24 grep 全部为 0, tracking: ADR-0169-task-25)
# 兼容窗口:web-standard 业务迁移(PR-21~24)期间,coord.* 必须继续工作。
# 删除条件:``grep -rn "coord.begin_step|coord.record_thinking" lca/cognition lca/body lca/runtime lca/agent`` 输出 0。
"""

from __future__ import annotations

import hashlib
import json
from contextvars import ContextVar, Token
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

_DIGEST_PREFIX = "sha256:"


def sha256_digest(payload: Any) -> str:
    """Stable digest in ``sha256:<hex>`` form — JSON 序列化 → sha256。

    ADR-0185 PR-4 收口后为 ``sha256:<hex>`` digest 形态的唯一实现(承接
    旁路 capture 退场前的同名 helper)。``ensure_ascii=False`` 保持
    原字节级行为:非 ASCII 内容 digest 不因序列化转义改变。
    """
    encoded = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return _DIGEST_PREFIX + hashlib.sha256(encoded).hexdigest()


# COMPAT(delete-when: PR-21~24 grep 全部为 0, tracking: ADR-0169-task-25)
# 当前 cursor 由 CoordinatorAdapter 持有;PR-21~24 业务迁 cursor 期间,
# 业务路径(perceive_hub / safe_executor / tool_journal_emit)取 cursor 走本
# ContextVar —— 由 wiring 层在 RunExecutionEnvironment.prepare 阶段 set。
# 删除条件:业务代码全迁完 cursor 后,直接传 cursor 参数替换 ContextVar 访问。
_current_cursor: ContextVar[LoopCursor | None] = ContextVar("lca_loop_cursor_current", default=None)


def get_current_cursor() -> LoopCursor | None:
    """取当前 run 绑定的 LoopCursor(PR-26 业务迁 cursor 入口)。"""
    return _current_cursor.get()


def bind_current_cursor(cursor: LoopCursor) -> Token[LoopCursor | None]:
    """绑定 cursor;返回 reset token,由调用方在 finally 释放。"""
    return _current_cursor.set(cursor)


def reset_current_cursor(token: Any) -> None:
    _current_cursor.reset(token)


# 兼容旧名:PR-26 业务代码用 current_cursor() 访问;保留别名便于增量迁移。
def current_cursor() -> LoopCursor | None:
    return _current_cursor.get()


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
        if snap.phase != phase:
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

    # ── record_*: 同时调 cursor + coord(双写) ──────────────────

    def record_thinking(self, trace: ThinkingTrace) -> None:
        """``record_thinking`` —— cursor 唯一 writer(SSOT 收口)。

        journal_step ``ThinkingTrace`` 字段 = model / latency_ms / reasoning /
        decision / tool_call / prompt_tokens / completion_tokens /
        raw_response_preview;cursor ``ThinkingRecord`` 字段 = content_digest /
        content_path / token_count / thinking_kind。映射:
            content_digest ← sha256:<hex> via sha256_digest
            content_path   ← None
            token_count    ← prompt_tokens + completion_tokens
            thinking_kind  ← "reasoning"
        """
        prompt_tokens = getattr(trace, "prompt_tokens", 0) or 0
        completion_tokens = getattr(trace, "completion_tokens", 0) or 0
        token_count = prompt_tokens + completion_tokens or None
        reasoning_text = getattr(trace, "reasoning", "") or ""
        self._cursor.record_thinking(
            ThinkingRecord(
                content_digest=sha256_digest({"reasoning": reasoning_text}),
                content_path=None,
                token_count=token_count,
                thinking_kind="reasoning",
            )
        )

    def record_tool_call(self, call: LegacyToolCallRecord) -> None:
        """``record_tool_call`` —— cursor 唯一 writer。

        journal_step ``ToolCallRecord`` 字段 = invocation_id / name / arguments /
        arguments_summary;cursor ``ToolCallRecord`` 字段 = tool_name / args_digest /
        args_payload_path / call_seq。映射:
            tool_name       ← name
            args_digest     ← sha256:<hex> via sha256_digest
            args_payload_path ← None(arguments 内容由 payload adapter 处理)
            call_seq        ← cursor's monotonic seq
        """
        tool_name = getattr(call, "name", "")
        invocation_id = getattr(call, "invocation_id", "") or ""
        args_summary = getattr(call, "arguments_summary", "") or ""
        arguments = getattr(call, "arguments", None) or {}
        self._cursor.record_tool_call(
            ToolCallRecord(
                tool_name=tool_name,
                args_digest=sha256_digest({"args": args_summary, "invocation_id": invocation_id}),
                args_payload_path=None,
                call_seq=self._cursor.snapshot.seq,
            ),
            arguments=arguments,
            arguments_summary=args_summary,
            invocation_id=invocation_id,
        )

    def record_tool_result(self, result: LegacyToolResult) -> None:
        """``record_tool_result`` —— cursor 唯一 writer。

        journal_step ``ToolResult`` 没有 ``tool_name`` 字段(由 caller 上下文
        提供);cursor ``ToolResultRecord`` 必填 tool_name,降级用空串。
        """
        ok = bool(getattr(result, "ok", True))
        outcome: str = "ok" if ok else "failure"
        tool_name = getattr(result, "tool_name", "") or ""
        delta_summary = getattr(result, "delta_summary", "") or ""
        latency_ms = int(getattr(result, "latency_ms", 0) or 0)
        stdout_head = getattr(result, "stdout_head", "") or ""
        stdout_chars_total = int(getattr(result, "stdout_chars_total", 0) or 0)
        stdout_truncated = bool(getattr(result, "stdout_truncated", False))
        stderr = getattr(result, "stderr", "") or ""
        files_created = getattr(result, "files_created", ()) or ()
        error = getattr(result, "error", None)
        self._cursor.record_tool_result(
            ToolResultRecord(
                tool_name=tool_name,
                result_digest=sha256_digest({"delta_summary": delta_summary}),
                result_path=None,
                outcome=outcome,  # type: ignore[arg-type]
            ),
            ok=ok,
            latency_ms=latency_ms,
            stdout_head=stdout_head,
            stdout_chars_total=stdout_chars_total,
            stdout_truncated=stdout_truncated,
            stderr=stderr,
            files_created=tuple(files_created),
            error=error,
            delta_summary=delta_summary,
        )

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


__all__ = [
    "CoordinatorAdapter",
    "bind_current_cursor",
    "current_cursor",
    "get_current_cursor",
    "reset_current_cursor",
]
