"""观测装饰器（Decorator 模式）—— 组合根装配，业务代码零埋点。

- ``TelemetryLLMAdapter``：LLM 调用 → journal ``LlmCallCompleted``
  （OTel 投影为 generation，gen_ai 语义约定 + token/成本自动核算）；
- ``TelemetryMemoryAdapter``：记忆读写 → memory.read / memory.write span
  （机制平面，verbose 档调试细节）。
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

from lca.contracts.atoms.enums import MemoryLayer
from lca.contracts.atoms.telemetry import (
    ATTR_HIT,
    ATTR_MEMORY_LAYER,
    SpanName,
)
from lca.contracts.models.core.decision import Observation, Reflection
from lca.contracts.models.core.llm import LLMResponse
from lca.contracts.models.core.memory import MemoryRecord
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.observability.journal import LlmCallCompleted
from lca.contracts.protocols import LLMAdapter, MemorySystem
from lca.layer0_infra.observability.facade import record, span

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


def _usage_of(response: LLMResponse) -> tuple[int, int]:
    usage = response.usage
    if usage is None:
        return 0, 0
    return usage.prompt_tokens or 0, usage.completion_tokens or 0


class TelemetryLLMAdapter(LLMAdapter):
    """装饰器：LLM 边界记录 LlmCallCompleted，不持有后端（ambient journal）。"""

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
        try:
            response = await self._inner.complete(prompt, **kwargs)
        except Exception:
            self._record(model, prompt, "", False, started, 0, 0)
            raise
        prompt_tokens, completion_tokens = _usage_of(response)
        self._record(model, prompt, response.text, True, started, prompt_tokens, completion_tokens)
        return response

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[str]:
        model = _model_label(self._inner)
        started = time.perf_counter()
        chunks: list[str] = []
        try:
            async for chunk in self._inner.stream(prompt, **kwargs):
                chunks.append(chunk)
                yield chunk
        except Exception:
            self._record(model, prompt, "".join(chunks), False, started, 0, 0)
            raise
        self._record(model, prompt, "".join(chunks), True, started, 0, 0)

    @staticmethod
    def _record(
        model: str,
        prompt: str,
        response_text: str,
        ok: bool,
        started: float,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> None:
        record(
            LlmCallCompleted(
                model=model,
                ok=ok,
                latency_ms=int((time.perf_counter() - started) * _PERF_COUNTER_SCALE),
                prompt_preview=prompt,
                response_preview=response_text,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
        )


_MEMORY_LAYER_PERCEIVE = "perceive"
_MEMORY_LAYER_UPDATE = "update"


class TelemetryMemoryAdapter(MemorySystem):
    """装饰器：记忆边界打 memory.read / memory.write span（机制平面）。"""

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
