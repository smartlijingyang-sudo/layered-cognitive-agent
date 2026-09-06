"""LLM spine EP emit seam — injected at composition root (ADR-0194 P2-13)."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from lca.contracts.models.core.state.state import AgentState


@runtime_checkable
class LlmSpineEmitter(Protocol):
    def emit_llm_call_start(
        self,
        *,
        model: str,
        stream: bool,
        prompt_preview: str = "",
        state: AgentState | None = None,
        session: object | None = None,
    ) -> Any: ...

    def emit_llm_call_end(
        self,
        *,
        model: str,
        stream: bool,
        outcome: str = "success",
        latency_ms: int = 0,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        state: AgentState | None = None,
        session: object | None = None,
    ) -> Any: ...

    def emit_llm_stream_token(
        self,
        *,
        model: str,
        text_delta: str,
        seq: int,
        channel_kind: str = "output",
        state: AgentState | None = None,
        session: object | None = None,
    ) -> Any: ...

    def emit_llm_stream_stall(
        self,
        *,
        model: str,
        idle_ms: int,
        seq: int = 0,
        state: AgentState | None = None,
        session: object | None = None,
    ) -> Any: ...


__all__ = ["LlmSpineEmitter"]
