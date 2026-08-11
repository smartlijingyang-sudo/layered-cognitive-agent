"""离线可跑的确定性 Mock LLM 实现。"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from typing import Any

from lca.contracts.atoms.enums import LLMStreamEventType
from lca.contracts.models.core.llm import LLMResponse, LLMStreamEvent, NativeToolCall
from lca.contracts.protocols import LLMAdapter

# Minimum token count (numbers + operators) to qualify as an arithmetic expression.
_MIN_ARITHMETIC_TOKENS = 3
_REASONING_CHUNK_SIZE = 12


def _chunk_text(text: str, *, size: int = _REASONING_CHUNK_SIZE) -> list[str]:
    if size <= 0 or not text:
        return [text] if text else []
    return [text[i : i + size] for i in range(0, len(text), size)]


class MockLLMAdapter(LLMAdapter):
    """确定性假 LLM，用于测试与演示；接口与真实厂商适配器完全一致。"""

    name = "mock-llm"

    def _respond(self, text: str) -> LLMResponse:
        return LLMResponse(text=text, model=self.name)

    def _respond_with_tool_call(
        self, call_id: str, name: str, arguments: dict[str, Any]
    ) -> LLMResponse:
        return LLMResponse(
            text="",
            model=self.name,
            tool_calls=[NativeToolCall(call_id=call_id, name=name, arguments=arguments)],
        )

    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        await asyncio.sleep(0)

        if "TOOL_RESULT:" in prompt:
            m = re.search(r"TOOL_RESULT:\s*([^\n]+)", prompt)
            tool_result = m.group(1).strip() if m else "未知"
            question = re.search(r"USER_TASK:\s*([^\n]+)", prompt)
            q = question.group(1).strip() if question else ""
            return self._respond(f"「{q}」的答案是 {tool_result}。")

        expr = self._extract_arithmetic_expression(prompt)
        if expr:
            return self._respond_with_tool_call(
                call_id="mock_call_1",
                name="calculator",
                arguments={"expression": expr},
            )

        return self._respond("这是一个通用问题，暂无可用工具，基于已有知识直接作答。")

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[LLMStreamEvent]:
        response = await self.complete(prompt, **kwargs)
        # Emit rationale as reasoning stream so UI Thinking panel works offline.
        if response.tool_calls:
            # For tool calls, emit the arguments as function call deltas
            for tc in response.tool_calls:
                args_json = json.dumps(tc.arguments, ensure_ascii=False)
                yield LLMStreamEvent(
                    type=LLMStreamEventType.FUNCTION_CALL_ARGUMENTS_DELTA,
                    tool_call_id=tc.call_id,
                    tool_name=tc.name,
                    arguments_delta=args_json,
                )
        else:
            # For text responses, stream character by character
            for char in response.text:
                yield LLMStreamEvent(type=LLMStreamEventType.OUTPUT_TEXT_DELTA, text=char)
        yield LLMStreamEvent(type=LLMStreamEventType.COMPLETED, response=response)

    @staticmethod
    def _extract_arithmetic_expression(prompt: str) -> str | None:
        m = re.search(r"USER_TASK:\s*([^\n]+)", prompt)
        if not m:
            return None
        text = m.group(1)
        text = (
            text.replace("乘以", "*").replace("加上", "+").replace("减去", "-").replace("除以", "/")
        )
        text = text.replace("×", "*").replace("÷", "/")
        nums_ops = re.findall(r"[\d.]+|[+\-*/]", text)
        if len(nums_ops) >= _MIN_ARITHMETIC_TOKENS:
            return "".join(nums_ops)
        return None
