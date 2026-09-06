"""LLM spine EP production (ADR-0194 P2-13).

Body tool EPs live in ``tool_journal_commit``; this module owns
``llm.call.*`` and ``llm.stream.*`` facts via FactGateway.
"""

from __future__ import annotations

from typing import Any

from lca.contracts.models.core.state import AgentState
from lca.loop.emit.spine.ep import SpineEmitRef, publish_spine_ep

_LLM_ACTOR = "llm"


def emit_llm_call_start(
    *,
    model: str,
    stream: bool,
    prompt_preview: str = "",
    state: AgentState | None = None,
    session: object | None = None,
) -> SpineEmitRef | None:
    return publish_spine_ep(
        "llm.call.start",
        {
            "model": model,
            "stream": stream,
            "prompt_preview": prompt_preview[:512],
        },
        channel="fact",
        actor=_LLM_ACTOR,
        state=state,
        session=session,
    )


def emit_llm_call_end(
    *,
    model: str,
    stream: bool,
    outcome: str = "success",
    latency_ms: int | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    state: AgentState | None = None,
    session: object | None = None,
) -> SpineEmitRef | None:
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
    return publish_spine_ep(
        "llm.call.end",
        payload,
        channel="fact",
        actor=_LLM_ACTOR,
        state=state,
        session=session,
    )


def emit_llm_stream_token(
    *,
    model: str,
    text_delta: str,
    seq: int,
    channel_kind: str = "output",
    state: AgentState | None = None,
    session: object | None = None,
) -> SpineEmitRef | None:
    return publish_spine_ep(
        "llm.stream.token",
        {
            "model": model,
            "text_delta": text_delta[:1024],
            "seq": seq,
            "channel_kind": channel_kind,
        },
        channel="fact",
        actor=_LLM_ACTOR,
        state=state,
        session=session,
    )


def emit_llm_stream_stall(
    *,
    model: str,
    idle_ms: int,
    seq: int = 0,
    state: AgentState | None = None,
    session: object | None = None,
) -> SpineEmitRef | None:
    return publish_spine_ep(
        "llm.stream.stall",
        {
            "model": model,
            "idle_ms": idle_ms,
            "seq": seq,
        },
        channel="diagnostic",
        actor=_LLM_ACTOR,
        state=state,
        session=session,
    )


__all__ = [
    "emit_llm_call_end",
    "emit_llm_call_start",
    "emit_llm_stream_stall",
    "emit_llm_stream_token",
]
