"""Body + LLM spine reflector — PR-3.3.

Emits canonical ``EXECUTION_POINTS`` events from the body layer (tool
execution and sandbox enter/exit) and the LLM layer (call start/end
and stream token). The module is the single emission site for these
eight execution points; the cognition/body/llm modules call the tiny
``emit_*`` helpers here before/after their public-method work and never
touch ``EventSpine.append`` directly.

Pattern
-------
Mirrors :mod:`lca.plugins.observability.spine.reflectors.cognition`:
helpers read the process-local active spine installed by
``set_active_spine`` and call ``spine.append(...)``. When no spine is
wired (default in unit tests), the helpers are silent no-ops — body
and LLM semantics and existing test surface are unchanged.

FD-1 / FD-2 containment
-----------------------
- ``emit_*`` wraps ``spine.append`` in ``try/except``. ``spine.append``
  follows FD-1 fail-fast on sink errors and FD-2 containment on
  deriver errors; the helper itself never adds another failure surface
  above it.
- ``EventRecord`` validation errors (e.g. malformed payload) raised
  by ``spine.append`` are contained here so body / LLM business logic
  is never blocked by a broken helper.

The module imports only the public spine surface (``EventSpine``,
``SpineContext``, ``EXECUTION_POINTS``) and the ``Outcome`` type. It
does NOT import the legacy journal facade or any
``journal.{engine,backends,stream,step}`` module — those are forbidden
by the brief.
"""

from __future__ import annotations

import logging
from typing import Any

from lca.infrastructure.observability.spine.event_record import (
    Channel,
    EventRecord,
    Outcome,
)
from lca.plugins.observability.spine._spine_safety import (
    get_active_spine,
    safe_append,
    set_active_spine,
)

log = logging.getLogger(__name__)

# `_safe_append` and the active-spine accessors live in
# `plugins.observability.spine._spine_safety` — the single
# source of truth across all reflector modules. Profile boot
# installs the run's EventSpine there so every body / LLM call
# can locate it without changing any constructor signature.

def _safe_append(
    *,
    execution_point: str,
    channel: Channel,
    payload: dict[str, Any] | None = None,
    outcome: Outcome | None = None,
) -> EventRecord | None:
    """Thin pass-through to the shared ``safe_append`` helper.

    Kept under the historic name for the ``emit_*`` helpers in this
    file. The shared implementation lives in ``_spine_safety``.
    """
    return safe_append(
        execution_point=execution_point,
        channel=channel,
        payload=payload,
        outcome=outcome,
    )

# ── body.tool.execute.start / body.tool.execute.end ─────────────────


def emit_body_tool_execute_start(
    *,
    tool_name: str,
    invocation_id: str,
    attempt: int = 1,
) -> EventRecord | None:
    """Emit ``body.tool.execute.start`` —— 真实 invocation 层（safe_executor 内部）。

    ADR-0166 S2：对外 spine 只表达 invocation；decision 层 wrapper 见
    :func:`emit_body_tool_decision_start`。
    """
    return _safe_append(
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
    outcome: Outcome = "success",
    latency_ms: int | None = None,
) -> EventRecord | None:
    """Emit ``body.tool.execute.end``（invocation 层，ADR-0166 S2）。"""
    payload: dict[str, Any] = {
        "tool_name": tool_name,
        "invocation_id": invocation_id,
        "attempt": attempt,
    }
    if latency_ms is not None:
        payload["latency_ms"] = latency_ms
    return _safe_append(
        execution_point="body.tool.execute.end",
        channel="control",
        payload=payload,
        outcome=outcome,
    )


def emit_body_tool_decision_start(
    *,
    tool_name: str,
    invocation_id: str,
) -> EventRecord | None:
    """decision wrapper 起点（ADR-0166 S2）。

    action-handler 层 batch dispatch 边；LiveTail / reader 默认折叠
    （payload 携带 ``wrapper=decision``）。
    """
    return _safe_append(
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
    outcome: Outcome = "success",
) -> EventRecord | None:
    """decision wrapper 终点（ADR-0166 S2）。"""
    return _safe_append(
        execution_point="body.tool.execute.end",
        channel="control",
        payload={
            "tool_name": tool_name,
            "invocation_id": invocation_id,
            "attempt": 1,
            "wrapper": "decision",
        },
        outcome=outcome,
    )


# ── body.tool.retry ──────────────────────────────────────────────────


def emit_body_tool_retry(
    *,
    tool_name: str,
    invocation_id: str,
    attempt: int,
    reason: str,
) -> EventRecord | None:
    return _safe_append(
        execution_point="body.tool.retry",
        channel="control",
        payload={
            "tool_name": tool_name,
            "invocation_id": invocation_id,
            "attempt": attempt,
            "reason": reason,
        },
        outcome="retrying",
    )


# ── body.sandbox.enter / body.sandbox.exit ───────────────────────────


def emit_body_sandbox_enter(
    *,
    invocation_id: str,
    tool_name: str,
) -> EventRecord | None:
    return _safe_append(
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
    outcome: Outcome = "success",
) -> EventRecord | None:
    return _safe_append(
        execution_point="body.sandbox.exit",
        channel="control",
        payload={
            "invocation_id": invocation_id,
            "tool_name": tool_name,
        },
        outcome=outcome,
    )


# ── llm.call.start / llm.call.end ────────────────────────────────────


def emit_llm_call_start(
    *,
    model: str,
    stream: bool,
    prompt_preview: str = "",
) -> EventRecord | None:
    return _safe_append(
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
    outcome: Outcome = "success",
    latency_ms: int | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
) -> EventRecord | None:
    payload: dict[str, Any] = {
        "model": model,
        "stream": stream,
    }
    if latency_ms is not None:
        payload["latency_ms"] = latency_ms
    if prompt_tokens is not None:
        payload["prompt_tokens"] = prompt_tokens
    if completion_tokens is not None:
        payload["completion_tokens"] = completion_tokens
    return _safe_append(
        execution_point="llm.call.end",
        channel="fact",
        payload=payload,
        outcome=outcome,
    )


# ── llm.stream.token ────────────────────────────────────────────────


def emit_llm_stream_token(
    *,
    model: str,
    text_delta: str,
    seq: int,
    channel_kind: str = "output",
) -> EventRecord | None:
    """Emit one streamed token.

    ``channel_kind`` distinguishes ``output`` (final answer) from
    ``reasoning`` (chain-of-thought) deltas; the helper does not
    interpret the value, just carries it through so downstream
    consumers can filter.
    """
    return _safe_append(
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
) -> EventRecord | None:
    """Emit when an in-flight LLM stream has produced no delta for a while.

    Complements journal ``RunActivity`` heartbeats so offline spine
    diagnosis can see provider stalls without the live journal tail.
    """
    return _safe_append(
        execution_point="llm.stream.stall",
        channel="diagnostic",
        payload={
            "model": model,
            "idle_ms": idle_ms,
            "seq": seq,
        },
    )


__all__ = [
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
    "get_active_spine",
    "set_active_spine",
]
