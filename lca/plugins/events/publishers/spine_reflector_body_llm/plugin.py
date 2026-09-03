"""spine_reflector_body_llm plugin（ADR-0181 PR-3 / ADR-0183 PR-7）。

PR-3：body + llm 全部 9 emit（tool.execute.start/end + retry + sandbox.enter/exit
+ decision.start/end + llm.call.start/end + llm.stream.token + llm.stream.stall）
下沉到 EventBus.publish；signature 严格对齐旧
lca/plugins/observability/spine/reflectors/body_llm.py 调用方零改动（仅
import 路径换到 lca.plugins.events.publishers.spine_reflector_body_llm）。

业务方一行调：
    EventBus.default().publish(
        SpineEventPayload(execution_point="...", channel="...", payload={...}),
        producer=ReflectorClass,
    )
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from lca_kernel.events.payloads import Category, SpineEventPayload
from lca_kernel.events.payloads_spine import _SPINE_EP_TO_CATEGORY

if TYPE_CHECKING:
    from lca_kernel.events.bus import EventRef

log = logging.getLogger(__name__)


class ReflectorClass:
    """publisher plugin 类（空标记类）。机制按 class 全路径鉴权。"""


def _send(
    *,
    execution_point: str,
    channel: str,
    payload: dict[str, Any],
) -> EventRef:
    """内部 helper：构造 SpineEventPayload + EventBus.publish。

    category 由 execution_point 通过 _SPINE_EP_TO_CATEGORY 派生。
    outcome（旧 reflector EventRecord.outcome）写进 payload，保留旧 API。

    注：EventBus import 走函数内 lazy，避免 lca_kernel.events 顶层
    被 lca.infrastructure.observability 启动时倒灌触发 circular import
    （lca_kernel.boot → lca.harness.observability → adapters →
    spine_reflector_body_llm）。
    """
    from lca_kernel.events.bus import EventBus

    cat_str = _SPINE_EP_TO_CATEGORY[execution_point]
    sp = SpineEventPayload(
        category=Category(cat_str),
        execution_point=execution_point,
        channel=channel,
        payload=payload,
    )
    return EventBus.default().publish(sp, producer=ReflectorClass)


# ── body.tool.execute.start / end（invocation 层，ADR-0166 S2）───────────


def emit_body_tool_execute_start(
    *,
    tool_name: str,
    invocation_id: str,
    attempt: int = 1,
) -> Any:
    """Emit ``body.tool.execute.start`` —— 真实 invocation 层（safe_executor 内部）。

    ADR-0166 S2：对外 spine 只表达 invocation；decision 层 wrapper 见
    :func:`emit_body_tool_decision_start`。
    """
    return _send(
        execution_point="body.tool.execute.start",
        channel="control",
        payload={
            "tool_name": tool_name,
            "invocation_id": invocation_id,
            "attempt": attempt,
        },
    )


def emit_body_tool_execute_end(
    *,
    tool_name: str,
    invocation_id: str,
    attempt: int = 1,
    outcome: str = "success",
    latency_ms: int | None = None,
) -> Any:
    """Emit ``body.tool.execute.end``（invocation 层，ADR-0166 S2）。"""
    payload: dict[str, Any] = {
        "tool_name": tool_name,
        "invocation_id": invocation_id,
        "attempt": attempt,
        "outcome": outcome,
    }
    if latency_ms is not None:
        payload["latency_ms"] = latency_ms
    return _send(
        execution_point="body.tool.execute.end",
        channel="control",
        payload=payload,
    )


# ── decision wrapper（ADR-0166 S2）─────────────────────────────────────


def emit_body_tool_decision_start(
    *,
    tool_name: str,
    invocation_id: str,
) -> Any:
    """decision wrapper 起点（ADR-0166 S2）。

    action-handler 层 batch dispatch 边；LiveTail / reader 默认折叠
    （payload 携带 ``wrapper=decision``）。
    """
    return _send(
        execution_point="body.tool.execute.start",
        channel="control",
        payload={
            "tool_name": tool_name,
            "invocation_id": invocation_id,
            "attempt": 1,
            "wrapper": "decision",
        },
    )


def emit_body_tool_decision_end(
    *,
    tool_name: str,
    invocation_id: str,
    outcome: str = "success",
) -> Any:
    """decision wrapper 终点（ADR-0166 S2）。"""
    return _send(
        execution_point="body.tool.execute.end",
        channel="control",
        payload={
            "tool_name": tool_name,
            "invocation_id": invocation_id,
            "attempt": 1,
            "wrapper": "decision",
            "outcome": outcome,
        },
    )


# ── body.tool.retry ───────────────────────────────────────────────────


def emit_body_tool_retry(
    *,
    tool_name: str,
    invocation_id: str,
    attempt: int,
    reason: str,
) -> Any:
    return _send(
        execution_point="body.tool.retry",
        channel="control",
        payload={
            "tool_name": tool_name,
            "invocation_id": invocation_id,
            "attempt": attempt,
            "reason": reason,
            "outcome": "retrying",
        },
    )


# ── body.sandbox.enter / body.sandbox.exit ─────────────────────────────


def emit_body_sandbox_enter(
    *,
    invocation_id: str,
    tool_name: str,
) -> Any:
    return _send(
        execution_point="body.sandbox.enter",
        channel="control",
        payload={
            "invocation_id": invocation_id,
            "tool_name": tool_name,
        },
    )


def emit_body_sandbox_exit(
    *,
    invocation_id: str,
    tool_name: str,
    outcome: str = "success",
) -> Any:
    return _send(
        execution_point="body.sandbox.exit",
        channel="control",
        payload={
            "invocation_id": invocation_id,
            "tool_name": tool_name,
            "outcome": outcome,
        },
    )


# ── llm.call.start / llm.call.end ──────────────────────────────────────


def emit_llm_call_start(
    *,
    model: str,
    stream: bool,
    prompt_preview: str = "",
) -> Any:
    return _send(
        execution_point="llm.call.start",
        channel="fact",
        payload={
            "model": model,
            "stream": stream,
            "prompt_preview": prompt_preview[:512],
        },
    )


def emit_llm_call_end(
    *,
    model: str,
    stream: bool,
    outcome: str = "success",
    latency_ms: int | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
) -> Any:
    payload: dict[str, Any] = {
        "model": model,
        "stream": stream,
        "outcome": outcome,
    }
    if latency_ms is not None:
        payload["latency_ms"] = latency_ms
    if prompt_tokens is not None:
        payload["prompt_tokens"] = prompt_tokens
    if completion_tokens is not None:
        payload["completion_tokens"] = completion_tokens
    return _send(
        execution_point="llm.call.end",
        channel="fact",
        payload=payload,
    )


# ── llm.stream.token / llm.stream.stall ───────────────────────────────


def emit_llm_stream_token(
    *,
    model: str,
    text_delta: str,
    seq: int,
    channel_kind: str = "output",
) -> Any:
    """Emit one streamed token.

    ``channel_kind`` distinguishes ``output`` (final answer) from
    ``reasoning`` (chain-of-thought) deltas; the helper does not
    interpret the value, just carries it through so downstream
    consumers can filter.
    """
    return _send(
        execution_point="llm.stream.token",
        channel="fact",
        payload={
            "model": model,
            "text_delta": text_delta[:1024],
            "seq": seq,
            "channel_kind": channel_kind,
        },
    )


def emit_llm_stream_stall(
    *,
    model: str,
    idle_ms: int,
    seq: int = 0,
) -> Any:
    """Emit when an in-flight LLM stream has produced no delta for a while.

    Complements journal ``RunActivity`` heartbeats so offline spine
    diagnosis can see provider stalls without the live journal tail.
    """
    return _send(
        execution_point="llm.stream.stall",
        channel="diagnostic",
        payload={
            "model": model,
            "idle_ms": idle_ms,
            "seq": seq,
        },
    )


__all__ = [
    "ReflectorClass",
    "emit_body_sandbox_enter",
    "emit_body_sandbox_exit",
    "emit_body_tool_decision_end",
    "emit_body_tool_decision_start",
    "emit_body_tool_execute_end",
    "emit_body_tool_execute_start",
    "emit_body_tool_retry",
    "emit_llm_call_end",
    "emit_llm_call_start",
    "emit_llm_stream_stall",
    "emit_llm_stream_token",
]
