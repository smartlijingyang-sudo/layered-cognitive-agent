"""DecisionParser —— 将自由文本/工具调用稳健地解析为强类型 StructuredDecision。"""

from __future__ import annotations

import json
import uuid
from typing import Any

from contracts.state import TypedState
from contracts.decision import StructuredDecision, ToolCall


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class SimpleDecisionParser:
    """JSON 解析器，失败时退化为直接 respond 原始文本。"""

    def parse(self, raw_output: str, state: TypedState) -> StructuredDecision:
        try:
            data = json.loads(raw_output)
            tool_call = None
            if data.get("action_type") == "use_tool":
                tool_call = ToolCall(
                    call_id=_new_id("call"),
                    tool_name=data["tool_name"],
                    arguments=data.get("arguments", {}),
                )
            return StructuredDecision(
                decision_id=_new_id("dec"),
                action_type=data["action_type"],
                tool_call=tool_call,
                response_text=data.get("response_text"),
                rationale=data.get("rationale", ""),
                confidence=float(data.get("confidence", 0.5)),
            )
        except (json.JSONDecodeError, KeyError):
            return StructuredDecision(
                decision_id=_new_id("dec"),
                action_type="respond",
                response_text=raw_output,
                rationale="解析失败兜底",
                confidence=0.1,
            )
