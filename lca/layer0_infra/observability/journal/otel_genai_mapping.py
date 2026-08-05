"""LLM 调用 → generation span 属性映射（gen_ai 语义约定 + Langfuse generation）。

从 ``otel_mapping`` 拆出的独立关注点：generation 的属性装配涉及 OpenTelemetry
GenAI 语义约定与 Langfuse token/成本自动核算约定，与一般 span 映射无关。
"""

from __future__ import annotations

import json
from typing import Any

from lca.contracts.journal import LlmCallCompleted
from lca.contracts.telemetry import (
    ATTR_COMPLETION_TOKENS,
    ATTR_LATENCY_MS,
    ATTR_MODEL,
    ATTR_OK,
    ATTR_PROMPT_PREVIEW,
    ATTR_PROMPT_TOKENS,
    ATTR_RESPONSE_PREVIEW,
)
from lca.layer0_infra.observability.journal.otel_mapping import drop_empty
from lca.layer0_infra.observability.langfuse_conventions import (
    GEN_AI_INPUT,
    GEN_AI_OPERATION,
    GEN_AI_OPERATION_CHAT,
    GEN_AI_OUTPUT,
    GEN_AI_REQUEST_MODEL,
    GEN_AI_USAGE_INPUT_TOKENS,
    GEN_AI_USAGE_OUTPUT_TOKENS,
    LANGFUSE_OBSERVATION_INPUT,
    LANGFUSE_OBSERVATION_MODEL_NAME,
    LANGFUSE_OBSERVATION_OUTPUT,
    LANGFUSE_OBSERVATION_TYPE,
    LANGFUSE_OBSERVATION_USAGE_DETAILS,
    OBSERVATION_TYPE_GENERATION,
)


def llm_call_attrs(event: LlmCallCompleted) -> dict[str, Any]:
    """generation span 属性：LCA 词表键 + gen_ai 语义约定 + Langfuse 映射。"""
    usage: dict[str, int] = {}
    if event.prompt_tokens:
        usage["input"] = event.prompt_tokens
    if event.completion_tokens:
        usage["output"] = event.completion_tokens
    return drop_empty(
        {
            ATTR_MODEL: event.model,
            ATTR_OK: event.ok,
            ATTR_LATENCY_MS: event.latency_ms,
            ATTR_PROMPT_PREVIEW: event.prompt_preview,
            ATTR_RESPONSE_PREVIEW: event.response_preview,
            ATTR_PROMPT_TOKENS: event.prompt_tokens,
            ATTR_COMPLETION_TOKENS: event.completion_tokens,
            GEN_AI_OPERATION: GEN_AI_OPERATION_CHAT,
            GEN_AI_REQUEST_MODEL: event.model,
            GEN_AI_INPUT: event.prompt_preview,
            GEN_AI_OUTPUT: event.response_preview,
            GEN_AI_USAGE_INPUT_TOKENS: event.prompt_tokens,
            GEN_AI_USAGE_OUTPUT_TOKENS: event.completion_tokens,
            LANGFUSE_OBSERVATION_TYPE: OBSERVATION_TYPE_GENERATION,
            LANGFUSE_OBSERVATION_MODEL_NAME: event.model,
            LANGFUSE_OBSERVATION_INPUT: event.prompt_preview,
            LANGFUSE_OBSERVATION_OUTPUT: event.response_preview,
            LANGFUSE_OBSERVATION_USAGE_DETAILS: json.dumps(usage) if usage else "",
        }
    )
