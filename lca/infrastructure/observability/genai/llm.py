"""LlmGenAIMapper —— LlmCallCompleted → gen_ai.* 属性。

包含 model / latency / tokens / TTFT 估算（暂时用 latency_ms 近似）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lca.infrastructure.observability.backends.langfuse_conventions import (
    GEN_AI_INPUT,
    GEN_AI_OPERATION,
    GEN_AI_OPERATION_CHAT,
    GEN_AI_OUTPUT,
    GEN_AI_REQUEST_MODEL,
    GEN_AI_USAGE_INPUT_TOKENS,
    GEN_AI_USAGE_OUTPUT_TOKENS,
)

if TYPE_CHECKING:
    from lca.contracts.models.observability.journal import StampedEvent


class LlmGenAIMapper:
    event_type = "LlmCallCompleted"
    runtime_kind = "llm"

    def map(self, stamped: StampedEvent) -> dict[str, str]:
        from lca.contracts.models.observability.journal import LlmCallCompleted

        event = stamped.event
        if not isinstance(event, LlmCallCompleted):
            return {}
        attrs: dict[str, str] = {
            GEN_AI_OPERATION: GEN_AI_OPERATION_CHAT,
            GEN_AI_REQUEST_MODEL: event.model,
        }
        if event.latency_ms:
            attrs["gen_ai.latency_ms"] = str(event.latency_ms)
        if event.prompt_preview:
            attrs[GEN_AI_INPUT] = event.prompt_preview
        if event.response_preview:
            attrs[GEN_AI_OUTPUT] = event.response_preview
        if event.prompt_tokens:
            attrs[GEN_AI_USAGE_INPUT_TOKENS] = str(event.prompt_tokens)
        if event.completion_tokens:
            attrs[GEN_AI_USAGE_OUTPUT_TOKENS] = str(event.completion_tokens)
        return attrs
