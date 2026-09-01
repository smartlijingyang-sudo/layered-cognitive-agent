"""Step Emitter —— cognitive emit 到 step_lifecycle 的桥接层(ADR-0164 草案 Phase 3)。

背景:
    原 emit 链(``TelemetryLLMAdapter`` / ``tool_journal_emit`` / ``perceive_hub``
    / ``event_emission``)直接调 ``facade.record(JournalEvent)``。 这是流式
    模型(每条事件一条 record)。

    新模型下, 这些事件应折叠进 step-tree:
        - ``LlmCallStarted/Completed`` + ``ReasoningDelta*`` + ``StepTextDelta*``
          → ``step.thinking`` (ThinkingTrace)
        - ``ToolStarted/Invoked`` + ``ToolDenied`` + ``SandboxOutputDelta``
          → ``step.tool_call`` + ``step.tool_result`` + ``step.spans``
        - ``ContextManifested`` → 进入 perceive step 的 context_before
        - ``StepCompleted`` → ``step_close(outcome="ok"/"fail")``

设计: **双写过渡**
    - 调用方仍调原 emit helper(``emit_tool_started`` 等), 不改 API。
    - helper 内部: 调原 ``record(JournalEvent)``(保持 stream 兼容) +
      调 ``step_lifecycle.record_*``(写 step-tree)。
    - step_lifecycle 没绑定时(测试 / 老路径)→ 静默跳过, 不破坏。
    - Phase 7 集中清理时, 删原 ``record`` 调用, 只留 step_lifecycle。

设计: **谁负责 open_step / close_step**
    - ``PerceiveHub.perceive()`` 调 ``step_open("perceive")`` + ``step_close("ok")``
    - ``TelemetryLLMAdapter._record()``(LLM 调用收口) 调 ``step_open("think")`` +
      ``step_close("ok")``(围绕 LLM 调用)
    - ``safe_executor`` 工具调用收口 调 ``step_open("act")`` + ``step_close("ok/fail")``
    - phase_graph runtime loop 暂时不动, 由 cognitive 层各自 open/close。
      重复 open / 重复 close 都 fail-fast(由 step_lifecycle 守卫)。

不做的事:
    - 不删任何旧 JournalEvent 类(Phase 7 才删)。
    - 不改 record(event) 的语义(流式 reader 还依赖它)。
    - 不替换 SSE / OTel projector 的数据源(stream 仍在)。
"""

from __future__ import annotations

import time
from typing import Any

import structlog

from lca.contracts.models.observability.journal_step import (
    ReflectTrace,
    SpanRecord,
    ThinkingTrace,
    ToolCallRecord,
    ToolResult,
    compute_duration_ms,
)

_log = structlog.get_logger(__name__)

# ── 内部: step_lifecycle 句柄 ──


def _try_get_current_step():
    """silent helper —— step_lifecycle 没绑定返回 None, 调用方决定是否走 fallback。"""
    try:
        from lca.infrastructure.observability.facade import step_get_lifecycle_store

        store = step_get_lifecycle_store()
        if store is None:
            return None
        return store.get_current_step()
    except (RuntimeError, ImportError):
        return None


def _safe_record_thinking(trace: ThinkingTrace) -> None:
    try:
        from lca.infrastructure.observability.facade import step_record_thinking

        step_record_thinking(trace)
    except (RuntimeError, ImportError):
        return None


def _safe_record_tool_call(call: ToolCallRecord) -> None:
    try:
        from lca.infrastructure.observability.facade import step_record_tool_call

        step_record_tool_call(call)
    except (RuntimeError, ImportError):
        return None


def _safe_record_tool_result(result: ToolResult) -> None:
    try:
        from lca.infrastructure.observability.facade import step_record_tool_result

        step_record_tool_result(result)
    except (RuntimeError, ImportError):
        return None


def _safe_record_span(span: SpanRecord) -> None:
    try:
        from lca.infrastructure.observability.facade import step_record_span

        step_record_span(span)
    except (RuntimeError, ImportError):
        return None


def _safe_record_reflect(reflect: ReflectTrace) -> None:
    try:
        from lca.infrastructure.observability.facade import step_record_reflect

        step_record_reflect(reflect)
    except (RuntimeError, ImportError):
        return None


def _safe_open_step(
    phase: str,
    *,
    context: Any | None = None,
    subagent_role: str | None = None,
):
    """silent open step —— facade RuntimeError 也吞(没绑 _run_context 等)。"""
    try:
        from lca.infrastructure.observability.facade import step_open

        return step_open(
            phase,
            subagent_role=subagent_role,
            context=context,
        )
    except RuntimeError as exc:
        # facade 守卫: _require_run_bound 抛 RuntimeError → silent 跳过
        _log.debug(
            "step_open_skipped",
            phase=phase,
            reason=str(exc),
        )
        return None
    except ImportError:
        return None


def _safe_close_step(outcome: str, *, error: str | None = None):
    try:
        from lca.infrastructure.observability.facade import step_close

        return step_close(outcome, error=error)
    except (RuntimeError, ImportError):
        return None


# ── LLM bridge: emit LlmCallCompleted → step.thinking ──


def bridge_llm_completed(
    *,
    model: str,
    latency_ms: int,
    reasoning_preview: str = "",
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    response_preview: str = "",
    decision: str = "",
    tool_call: ToolCallRecord | None = None,
) -> None:
    """LLM 调用收口: record LlmCallCompleted + step_record_thinking。

    调用方: ``TelemetryLLMAdapter._record()``。
    """
    # 写 step.thinking —— 优先用 LLM call 的完整 reasoning + decision + tool_call
    trace = ThinkingTrace(
        model=model,
        latency_ms=latency_ms,
        reasoning=reasoning_preview,
        decision=decision,
        tool_call=tool_call,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        raw_response_preview=response_preview,
    )
    _safe_record_thinking(trace)


def bridge_llm_reasoning_delta(*, text_delta: str, started_at: float) -> None:
    """流式 reasoning 增量 → step span。

    不直接调 step.record_thinking(那样会反复覆盖), 改记 span 让 projector
    知道这是增量流(由 reader 自己拼)。
    """
    span = SpanRecord(
        kind="reasoning_delta",
        started_at=started_at,
        summary={"text_delta": text_delta},
    )
    _safe_record_span(span)


def bridge_llm_step_text_delta(*, text_delta: str, channel: str, started_at: float) -> None:
    """流式 step text 增量 → step span。"""
    span = SpanRecord(
        kind=f"step_text_delta:{channel}",
        started_at=started_at,
        summary={"text_delta": text_delta},
    )
    _safe_record_span(span)


# ── 工具 bridge: emit ToolStarted/Invoked/Denied → step.tool_call/tool_result ──


def bridge_tool_started(
    *,
    tool_name: str,
    invocation_id: str,
    arguments: dict[str, Any],
    arguments_summary: str = "",
) -> None:
    _safe_record_tool_call(
        ToolCallRecord(
            invocation_id=invocation_id,
            name=tool_name,
            arguments=arguments,
            arguments_summary=arguments_summary,
        ),
    )


def bridge_tool_invoked(
    *,
    tool_name: str,
    invocation_id: str,
    ok: bool,
    latency_ms: int,
    error: str | None = None,
    files_created: tuple[str, ...] = (),
    delta_summary: str = "",
    stdout_head: str = "",
    stderr: str = "",
    stdout_chars_total: int = 0,
    stdout_truncated: bool = False,
) -> None:
    _safe_record_tool_result(
        ToolResult(
            ok=ok,
            latency_ms=latency_ms,
            stdout_head=stdout_head,
            stdout_chars_total=stdout_chars_total,
            stdout_truncated=stdout_truncated,
            stderr=stderr,
            files_created=files_created,
            error=error,
            delta_summary=delta_summary,
        ),
    )


def bridge_tool_denied(*, tool_name: str, reason: str) -> None:
    """ToolDenied 折叠为 step span(失败但没结果)。"""
    span = SpanRecord(
        kind="tool_denied",
        started_at=time.time(),
        summary={"tool_name": tool_name, "reason": reason},
    )
    _safe_record_span(span)


# ── perceive bridge: emit ContextManifested → step_open("perceive") ──


def bridge_perceive_opened(*, objective: str) -> object | None:
    """perceive 入口: open step "perceive"。

    调用方: ``PerceiveHub.perceive()`` 开头。
    """
    from lca.contracts.models.observability.journal_step import (
        StepContext,
    )

    return _safe_open_step(
        "perceive",
        context=StepContext(objective=objective),
    )


def bridge_perceive_closed(*, outcome: str = "ok", summary: str = "") -> None:
    """perceive 出口: close step。"""
    if summary:
        _safe_record_reflect(ReflectTrace(summary=summary))
    _safe_close_step(outcome)


# ── think bridge: LLM 调用 = 一个 think step ──


def bridge_think_opened(*, objective: str) -> object | None:
    """LLM 调用入口: open step "think"。

    调用方: ``TelemetryLLMAdapter._record()`` 第一次调用时(模型拿到响应)。
    """
    from lca.contracts.models.observability.journal_step import StepContext

    return _safe_open_step(
        "think",
        context=StepContext(objective=objective),
    )


def bridge_think_closed(*, outcome: str = "ok", summary: str = "") -> None:
    if summary:
        _safe_record_reflect(ReflectTrace(summary=summary))
    _safe_close_step(outcome)


# ── act bridge: 工具调用 = 一个 act step ──


def bridge_act_opened(*, objective: str, tool_name: str = "") -> object | None:
    """工具调用入口: open step "act"。

    调用方: ``safe_executor.execute()`` 开始时。
    """
    from lca.contracts.models.observability.journal_step import StepContext

    return _safe_open_step(
        "act",
        context=StepContext(
            objective=objective,
            extra={"initiated_tool": tool_name},
        ),
    )


def bridge_act_closed(*, outcome: str = "ok", error: str | None = None, summary: str = "") -> None:
    if summary:
        _safe_record_reflect(ReflectTrace(summary=summary))
    _safe_close_step(outcome, error=error)


# ── step helper: bridge for "think 决定 + tool_call + tool_result" 三步合一 ──


def bridge_step_completed_emitted(*, status: str) -> None:
    """原 ``StepCompleted`` journal 事件的桥接 → close 当前 step。

    runtime / event_emission 仍写 StepCompleted 流式记录(stream 兼容),
    同时 close 当前 step。 当前 step 是哪个 phase 由调用方上下文决定。
    """
    outcome = "ok" if status not in ("failed", "fail", "error") else "fail"
    _safe_close_step(outcome)


__all__ = [
    # 内部 helper(测试可能用到)
    "_try_get_current_step",
    "bridge_act_closed",
    "bridge_act_opened",
    # LLM
    "bridge_llm_completed",
    "bridge_llm_reasoning_delta",
    "bridge_llm_step_text_delta",
    "bridge_perceive_closed",
    # Perceive / Think / Act step 边界
    "bridge_perceive_opened",
    # StepCompleted 兼容桥
    "bridge_step_completed_emitted",
    "bridge_think_closed",
    "bridge_think_opened",
    "bridge_tool_denied",
    "bridge_tool_invoked",
    # Tool
    "bridge_tool_started",
    # 计算 helper
    "compute_duration_ms",
]
