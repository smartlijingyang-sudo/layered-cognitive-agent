"""观测装饰器（Decorator 模式）—— 组合根装配，业务代码零埋点。

- ``TelemetryLLMAdapter``：LLM 调用 → llm.chat span（含 gen_ai 语义约定，
  Langfuse/任何 OTel GenAI 后端自动识别 generation 与 token 用量）；
- ``TelemetryMemoryAdapter``：记忆读写 → memory.read / memory.write span
  （知识检索可观测）。
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

from lca.contracts.decision import Observation, Reflection
from lca.contracts.enums import MemoryLayer
from lca.contracts.llm import LLMResponse
from lca.contracts.memory import MemoryRecord
from lca.contracts.protocols import LLMAdapter, MemorySystem
from lca.contracts.state import AgentState
from lca.contracts.telemetry import (
    ATTR_COMPLETION_TOKENS,
    ATTR_HIT,
    ATTR_LATENCY_MS,
    ATTR_MEMORY_LAYER,
    ATTR_MODEL,
    ATTR_OK,
    ATTR_PROMPT_CHARS,
    ATTR_PROMPT_PREVIEW,
    ATTR_PROMPT_TOKENS,
    ATTR_RESPONSE_CHARS,
    ATTR_RESPONSE_PREVIEW,
    SpanName,
)
from lca.layer0_infra.observability.facade import span

# OpenTelemetry GenAI 语义约定（业界标准键名，非 LCA 词表）
_GEN_AI_OPERATION = "gen_ai.operation.name"
_GEN_AI_OPERATION_CHAT = "chat"
_GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
_GEN_AI_INPUT = "gen_ai.input"
_GEN_AI_OUTPUT = "gen_ai.output"
_GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
_GEN_AI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"

# Langfuse OTel 观测约定（v4 服务端按此映射 generation 字段）
_LANGFUSE_OBSERVATION_TYPE = "langfuse.observation.type"
_LANGFUSE_OBSERVATION_MODEL = "langfuse.observation.model.name"
_LANGFUSE_OBSERVATION_INPUT = "langfuse.observation.input"
_LANGFUSE_OBSERVATION_OUTPUT = "langfuse.observation.output"
_LANGFUSE_OBSERVATION_USAGE = "langfuse.observation.usage_details"
_OBSERVATION_TYPE_GENERATION = "generation"

_PERF_COUNTER_SCALE = 1000
"""perf_counter 秒 → 毫秒换算。"""


def _model_label(inner: LLMAdapter) -> str:
    model = getattr(inner, "_model", None)
    if isinstance(model, str) and model:
        return model
    name = getattr(inner, "name", None)
    if isinstance(name, str) and name:
        return name
    return type(inner).__name__


class TelemetryLLMAdapter(LLMAdapter):
    """装饰器：LLM 边界打 llm.chat span，不持有后端（ambient Telemetry）。"""

    name = "telemetry-llm"

    def __init__(self, inner: LLMAdapter) -> None:
        self._inner = inner
        self.name = f"telemetry({getattr(inner, 'name', type(inner).__name__)})"

    @property
    def inner(self) -> LLMAdapter:
        """被装饰的 LLM 适配器（组合无损性内省用）。"""
        return self._inner

    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        model = _model_label(self._inner)
        started = time.perf_counter()
        with span(
            SpanName.LLM_CHAT,
            **{
                ATTR_MODEL: model,
                _GEN_AI_OPERATION: _GEN_AI_OPERATION_CHAT,
                _GEN_AI_REQUEST_MODEL: model,
                _GEN_AI_INPUT: prompt,
                _LANGFUSE_OBSERVATION_TYPE: _OBSERVATION_TYPE_GENERATION,
                _LANGFUSE_OBSERVATION_MODEL: model,
                _LANGFUSE_OBSERVATION_INPUT: prompt,
            },
        ) as handle:
            attrs = handle.attributes
            attrs[ATTR_PROMPT_CHARS] = len(prompt)
            attrs[ATTR_PROMPT_PREVIEW] = prompt
            try:
                response = await self._inner.complete(prompt, **kwargs)
            except Exception:
                attrs[ATTR_OK] = False
                attrs[ATTR_LATENCY_MS] = int((time.perf_counter() - started) * _PERF_COUNTER_SCALE)
                raise
            attrs[ATTR_OK] = True
            attrs[ATTR_LATENCY_MS] = int((time.perf_counter() - started) * _PERF_COUNTER_SCALE)
            attrs[ATTR_RESPONSE_CHARS] = len(response.text)
            attrs[ATTR_RESPONSE_PREVIEW] = response.text
            attrs[_GEN_AI_OUTPUT] = response.text
            attrs[_LANGFUSE_OBSERVATION_OUTPUT] = response.text
            self._record_usage(attrs, response)
            return response

    @staticmethod
    def _record_usage(attrs: dict[str, Any], response: LLMResponse) -> None:
        usage = response.usage
        if usage is None:
            return
        if usage.prompt_tokens is not None:
            attrs[ATTR_PROMPT_TOKENS] = usage.prompt_tokens
            attrs[_GEN_AI_USAGE_INPUT_TOKENS] = usage.prompt_tokens
        if usage.completion_tokens is not None:
            attrs[ATTR_COMPLETION_TOKENS] = usage.completion_tokens
            attrs[_GEN_AI_USAGE_OUTPUT_TOKENS] = usage.completion_tokens
        details: dict[str, int] = {}
        if usage.prompt_tokens is not None:
            details["input"] = usage.prompt_tokens
        if usage.completion_tokens is not None:
            details["output"] = usage.completion_tokens
        if details:
            attrs[_LANGFUSE_OBSERVATION_USAGE] = json.dumps(details)

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[str]:
        model = _model_label(self._inner)
        started = time.perf_counter()
        chunks: list[str] = []
        with span(
            SpanName.LLM_CHAT,
            **{
                ATTR_MODEL: model,
                "stream": True,
                _GEN_AI_OPERATION: _GEN_AI_OPERATION_CHAT,
                _GEN_AI_REQUEST_MODEL: model,
                _GEN_AI_INPUT: prompt,
                _LANGFUSE_OBSERVATION_TYPE: _OBSERVATION_TYPE_GENERATION,
                _LANGFUSE_OBSERVATION_MODEL: model,
                _LANGFUSE_OBSERVATION_INPUT: prompt,
            },
        ) as handle:
            attrs = handle.attributes
            attrs[ATTR_PROMPT_CHARS] = len(prompt)
            attrs[ATTR_PROMPT_PREVIEW] = prompt
            try:
                async for chunk in self._inner.stream(prompt, **kwargs):
                    chunks.append(chunk)
                    yield chunk
            except Exception:
                attrs[ATTR_OK] = False
                attrs[ATTR_LATENCY_MS] = int((time.perf_counter() - started) * _PERF_COUNTER_SCALE)
                raise
            text = "".join(chunks)
            attrs[ATTR_OK] = True
            attrs[ATTR_LATENCY_MS] = int((time.perf_counter() - started) * _PERF_COUNTER_SCALE)
            attrs[ATTR_RESPONSE_CHARS] = len(text)
            attrs[ATTR_RESPONSE_PREVIEW] = text
            attrs[_GEN_AI_OUTPUT] = text
            attrs[_LANGFUSE_OBSERVATION_OUTPUT] = text


_MEMORY_LAYER_PERCEIVE = "perceive"
_MEMORY_LAYER_UPDATE = "update"


class TelemetryMemoryAdapter(MemorySystem):
    """装饰器：记忆边界打 memory.read / memory.write span（知识检索可观测）。"""

    def __init__(self, inner: MemorySystem) -> None:
        self._inner = inner

    @property
    def inner(self) -> MemorySystem:
        """被装饰的记忆系统（组合无损性内省用）。"""
        return self._inner

    async def perceive(self, state: AgentState) -> AgentState:
        with span(SpanName.MEMORY_READ, **{ATTR_MEMORY_LAYER: _MEMORY_LAYER_PERCEIVE}) as handle:
            result = await self._inner.perceive(state)
            handle.attributes[ATTR_HIT] = bool(getattr(result, "retrieved_context", None))
            return result

    async def update(
        self, state: AgentState, observation: Observation, reflection: Reflection
    ) -> None:
        with span(SpanName.MEMORY_WRITE, **{ATTR_MEMORY_LAYER: _MEMORY_LAYER_UPDATE}):
            await self._inner.update(state, observation, reflection)

    def query(self, layer: MemoryLayer) -> list[MemoryRecord]:
        with span(SpanName.MEMORY_READ, **{ATTR_MEMORY_LAYER: layer.value}) as handle:
            records = self._inner.query(layer)
            handle.attributes[ATTR_HIT] = bool(records)
            return records
