"""llm seam Definition — owns ctx.llm; Providers register adapters."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from lca.contracts.atoms.enums import LLMStreamEventType
from lca.contracts.models.core.llm import LLMResponse, LLMStreamEvent
from lca.contracts.protocols import LLMAdapter
from lca.layer0_infra.capability.dispatch import ProviderDispatch


class LlmService(LLMAdapter):
    """Service Definition for LLM. Consumer 只依赖本类 / LLMAdapter。"""

    def __init__(self) -> None:
        self.providers = ProviderDispatch[LLMAdapter]("llm")

    def register(self, name: str, provider: LLMAdapter, *, activate: bool = False) -> None:
        self.providers.register(name, provider, activate=activate)

    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        return await self.providers.current().complete(prompt, **kwargs)

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[LLMStreamEvent]:
        adapter = self.providers.current()
        stream = adapter.stream
        async for event in stream(prompt, **kwargs):
            yield event
        if False:  # pragma: no cover — keeps Protocol generator shape
            yield LLMStreamEvent(type=LLMStreamEventType.COMPLETED)
