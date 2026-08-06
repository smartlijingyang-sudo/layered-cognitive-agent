"""模块私有 Strategy Protocol —— 不进 contracts。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol

from lca.contracts.models.core.llm import LLMResponse, LLMStreamEvent


class _ApiStrategy(Protocol):
    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse: ...

    def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[LLMStreamEvent]: ...
