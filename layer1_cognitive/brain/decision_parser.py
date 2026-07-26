"""DecisionParser —— 将自由文本/工具调用稳健地解析为强类型 StructuredDecision。"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any, Optional

from contracts.state import TypedState
from contracts.decision import StructuredDecision, ToolCall
from contracts.protocols import DecisionParser


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


_ACTION_ALIASES = {
    "tool_call": "use_tool",
    "call_tool": "use_tool",
    "use_tool": "use_tool",
    "respond": "respond",
    "response": "respond",
    "answer": "respond",
    "reply": "respond",
    "delegate": "delegate",
    "stop": "stop",
    "ask_human": "ask_human",
}


class SimpleDecisionParser(DecisionParser):
    """稳健 JSON 解析器：别名归一化 + markdown 代码块提取 + 失败兜底。"""

    def parse(self, raw_output: str, state: TypedState) -> StructuredDecision:
        json_str = self._extract_json(raw_output)
        try:
            data = json.loads(json_str)
        except (json.JSONDecodeError, ValueError):
            return StructuredDecision(
                decision_id=_new_id("dec"),
                action_type="respond",
                response_text=raw_output,
                rationale="解析失败兜底",
                confidence=0.1,
            )

        raw_action = str(data.get("action_type", "respond")).lower().strip()
        action_type = _ACTION_ALIASES.get(raw_action, raw_action)

        tool_call = None
        if action_type == "use_tool":
            tool_name = data.get("tool_name") or data.get("tool")
            arguments = data.get("arguments") or data.get("args") or data.get("parameters") or {}
            if not isinstance(arguments, dict):
                arguments = {"expression": str(arguments)}
            if tool_name:
                tool_call = ToolCall(
                    call_id=_new_id("call"),
                    tool_name=tool_name,
                    arguments=arguments,
                )
            else:
                action_type = "respond"

        return StructuredDecision(
            decision_id=_new_id("dec"),
            action_type=action_type,  # type: ignore[arg-type]
            tool_call=tool_call,
            response_text=data.get("response_text") or data.get("response") or data.get("text"),
            rationale=data.get("rationale", ""),
            confidence=float(data.get("confidence", 0.5)),
        )

    @staticmethod
    def _extract_json(text: str) -> str:
        m = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
        if m:
            return m.group(1).strip()
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return m.group(0)
        return text.strip()
