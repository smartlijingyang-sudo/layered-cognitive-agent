"""DecisionParser —— 将自由文本/工具调用稳健地解析为强类型 StructuredDecision。

L2 防腐层：所有 LLM 原始输出必须先经过此层归一化，
才能进入系统内部。核心域模型只看到已校验/已标记的决策。
"""

from __future__ import annotations

import json
import re
import uuid

from lca.contracts.action import ActionRegistry
from lca.contracts.decision import DelegationSpec, StructuredDecision, ToolCall
from lca.contracts.protocols import DecisionParser
from lca.contracts.state import TypedState


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


_ACTION_ALIASES: dict[str, str] = {
    "tool_call": "use_tool",
    "call_tool": "use_tool",
    "use_tool": "use_tool",
    "respond": "respond",
    "response": "respond",
    "answer": "respond",
    "reply": "respond",
    "delegate": "delegate",
    "delegation": "delegate",
    "handoff": "handoff",
    "hand_off": "handoff",
    "stop": "stop",
    "ask_human": "ask_human",
    "hitl": "ask_human",
}

_UNRECOGNIZED_ACTION_KEY = "original_action_type"


class SimpleDecisionParser(DecisionParser):
    """稳健 JSON 解析器：别名归一化 + Registry 校验 + 失败兜底。

    当提供 ActionRegistry 时，解析器会校验 action_type 是否已注册；
    未注册的 action_type 不会被强行改写，而是在 extra 中标记原始值，
    交由韧性层（FallbackActionHandler）决定降级策略。
    """

    def __init__(self, action_registry: ActionRegistry | None = None) -> None:
        self._action_registry = action_registry

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

        # L2 防腐层：校验 action_type 是否在 Registry 已注册集合内
        extra: dict[str, str] = {}
        if self._action_registry is not None and not self._action_registry.is_registered(
            action_type
        ):
            extra[_UNRECOGNIZED_ACTION_KEY] = action_type

        tool_calls: list[ToolCall] = []
        if action_type == "use_tool":
            tool_name = data.get("tool_name") or data.get("tool")
            arguments = data.get("arguments") or data.get("args") or data.get("parameters") or {}
            if not isinstance(arguments, dict):
                arguments = {"expression": str(arguments)}
            if tool_name:
                tool_calls.append(
                    ToolCall(
                        call_id=_new_id("call"),
                        tool_name=tool_name,
                        arguments=arguments,
                    )
                )
            else:
                action_type = "respond"

        delegate_to: DelegationSpec | None = None
        if action_type in ("delegate", "handoff"):
            subtask = data.get("subtask", "")
            target_role = data.get("target_role")
            context_refs = data.get("context_refs") or data.get("context") or []
            if not isinstance(context_refs, list):
                context_refs = [str(context_refs)]
            delegate_to = DelegationSpec(
                subtask=subtask,
                target_role=target_role,
                context_refs=context_refs,
            )

        return StructuredDecision(
            decision_id=_new_id("dec"),
            action_type=action_type,
            tool_calls=tool_calls,
            delegate_to=delegate_to,
            response_text=data.get("response_text") or data.get("response") or data.get("text"),
            rationale=data.get("rationale", ""),
            confidence=float(data.get("confidence", 0.5)),
            extra=extra,
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
