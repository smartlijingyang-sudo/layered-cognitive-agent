"""离线可跑的确定性 Mock LLM 实现。"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from typing import Any

from lca.contracts.atoms.enums import LLMStreamEventType
from lca.contracts.models.core.llm import LLMResponse, LLMStreamEvent
from lca.contracts.protocols import LLMAdapter

_REASONING_CHUNK_SIZE = 12


def _chunk_text(text: str, *, size: int = _REASONING_CHUNK_SIZE) -> list[str]:
    if size <= 0 or not text:
        return [text] if text else []
    return [text[i : i + size] for i in range(0, len(text), size)]


def _last_tool_content(history: Any) -> str:
    if not isinstance(history, list):
        return ""
    for item in reversed(history):
        if not isinstance(item, dict) or item.get("role") != "tool":
            continue
        content = str(item.get("content") or "").strip()
        if content:
            return content
    return ""


class MockLLMAdapter(LLMAdapter):
    """确定性假 LLM，用于测试与演示；接口与真实厂商适配器完全一致。"""

    name = "mock-llm"

    def _respond(self, text: str) -> LLMResponse:
        return LLMResponse(text=text, model=self.name)

    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        await asyncio.sleep(0)

        tool_result = _last_tool_content(kwargs.get("history") or [])
        if tool_result:
            question = re.search(r"USER_TASK:\s*([^\n]+)", prompt)
            q = question.group(1).strip() if question else ""
            return self._respond(f"「{q}」的答案是 {tool_result}。")

        return self._respond("这是一个通用问题，暂无可用工具，基于已有知识直接作答。")

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[LLMStreamEvent]:
        response = await self.complete(prompt, **kwargs)
        for char in response.text:
            yield LLMStreamEvent(type=LLMStreamEventType.OUTPUT_TEXT_DELTA, text=char)
        yield LLMStreamEvent(type=LLMStreamEventType.COMPLETED, response=response)
