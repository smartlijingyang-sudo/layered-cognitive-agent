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
from lca.infrastructure.observability.spine.event_spine import EventSpine

log = logging.getLogger(__name__)


# ── process-local active spine accessor ─────────────────────────────
#
# The body and LLM layers never receive the spine through their Protocol
# surface (Body / SafeExecutor / Tool / LLMAdapter). Profile boot
# installs the run's EventSpine here so every body / LLM call can
# locate it without changing any constructor signature. Tests call the
# setter directly to inject a capturing sink.

_active_spine: EventSpine | None = None


def set_active_spine(spine: EventSpine | None) -> None:
    """Install or clear the process-local active spine for body/LLM emits."""
    global _active_spine
    _active_spine = spine


def get_active_spine() -> EventSpine | None:
    """Return the active spine, or ``None`` if no run is in flight."""
    return _active_spine


# ── core emitter ──────────────────────────────────────────────────────


def _safe_append(
    *,
    execution_point: str,
    channel: Channel,
    payload: dict[str, Any] | None = None,
    outcome: Outcome | None = None,
) -> EventRecord | None:
    """Dispatch to the active spine, returning ``None`` when no spine wired.

    Swallows ``EventRecord`` validation errors (malformed payload) so a
    broken helper never blocks the caller; logs at WARNING. All other
    exceptions propagate as FD-1.
    """
    spine = _active_spine
    if spine is None:
        return None
    try:
        return spine.append(
            execution_point=execution_point,
            channel=channel,
            caller_payload=payload,
            outcome=outcome,
        )
    except ValueError as exc:
        # EventRecord post-init validation failure (e.g. unknown EP).
        log.warning(
            "body_llm_reflector: drop invalid event ep=%s err=%s",
            execution_point,
            exc,
        )
        return None


# ── body.tool.execute.start / body.tool.execute.end ─────────────────


def emit_body_tool_execute_start(
    *,
    tool_name: str,
    invocation_id: str,
    attempt: int = 1,
) -> EventRecord | None:
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


__all__ = [
    "emit_body_sandbox_enter",
    "emit_body_sandbox_exit",
    "emit_body_tool_execute_end",
    "emit_body_tool_execute_start",
    "emit_body_tool_retry",
    "emit_llm_call_end",
    "emit_llm_call_start",
    "emit_llm_stream_token",
    "get_active_spine",
    "set_active_spine",
]
