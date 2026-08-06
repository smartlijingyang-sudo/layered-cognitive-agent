"""离线可跑的确定性 Mock LLM 实现。"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from typing import Any

from lca.contracts.models.core.llm import LLMResponse
from lca.contracts.protocols import LLMAdapter

# Minimum token count (numbers + operators) to qualify as an arithmetic expression.
_MIN_ARITHMETIC_TOKENS = 3


class MockLLMAdapter(LLMAdapter):
    """确定性假 LLM，用于测试与演示；接口与真实厂商适配器完全一致。"""

    name = "mock-llm"

    def _respond(self, text: str) -> LLMResponse:
        return LLMResponse(text=text, model=self.name)

    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        await asyncio.sleep(0)

        if "TOOL_RESULT:" in prompt:
            m = re.search(r"TOOL_RESULT:\s*([^\n]+)", prompt)
            tool_result = m.group(1).strip() if m else "未知"
            question = re.search(r"USER_TASK:\s*([^\n]+)", prompt)
            q = question.group(1).strip() if question else ""
            return self._respond(
                json.dumps(
                    {
                        "action_type": "respond",
                        "response_text": f"「{q}」的答案是 {tool_result}。",
                        "rationale": "已从工具获得精确计算结果，直接向用户作答，无需进一步调用工具。",
                        "confidence": 0.98,
                    },
                    ensure_ascii=False,
                )
            )

        expr = self._extract_arithmetic_expression(prompt)
        if expr:
            return self._respond(
                json.dumps(
                    {
                        "action_type": "use_tool",
                        "tool_name": "calculator",
                        "arguments": {"expression": expr},
                        "rationale": f"用户问题是纯算术计算（{expr}），应调用 calculator 工具求精确值而非直接臆测。",
                        "confidence": 0.95,
                    },
                    ensure_ascii=False,
                )
            )

        return self._respond(
            json.dumps(
                {
                    "action_type": "respond",
                    "response_text": "这是一个通用问题，暂无可用工具，基于已有知识直接作答。",
                    "rationale": "未检测到需要调用工具的模式，直接生成回答。",
                    "confidence": 0.6,
                },
                ensure_ascii=False,
            )
        )

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[str]:
        response = await self.complete(prompt, **kwargs)
        for char in response.text:
            yield char

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
