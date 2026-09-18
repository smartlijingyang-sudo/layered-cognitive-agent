"""Per-assistant model override (ADR-0242 D9 / PR-8).

The boot-scoped LLM resolver is assistant-agnostic; per-assistant model
selection is Home data (``profile.json.model``). This thin wrapper injects
the assistant's model into every ``complete`` / ``stream`` call unless the
caller already passed an explicit ``model`` kwarg, so wire strategies keep
their own default fallback (I-B9: 运行时/全局配置只提供默认值).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from lca.contracts.models.core.conversation.llm import LLMResponse, LLMStreamEvent
from lca.contracts.protocols import LLMAdapter


class ModelOverridingLLMAdapter(LLMAdapter):
    """Thin ``LLMAdapter`` wrapper that defaults ``model`` to a Home value.

    Delegates ``complete`` / ``stream`` to the wrapped adapter after
    ``kwargs.setdefault("model", self._model)``. Exposes ``_model`` so
    ``TelemetryLLMAdapter._model_label`` can label assistant-selected models
    instead of the boot default.
    """

    def __init__(self, *, inner: LLMAdapter, model: str) -> None:
        if not model or not model.strip():
            raise ValueError("model 必须为非空字符串")
        self._inner = inner
        self._model = model

    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        kwargs.setdefault("model", self._model)
        return await self._inner.complete(prompt, **kwargs)

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[LLMStreamEvent]:
        kwargs.setdefault("model", self._model)
        async for event in self._inner.stream(prompt, **kwargs):
            yield event


__all__ = ["ModelOverridingLLMAdapter"]
