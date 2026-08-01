"""DecisionParser —— 将自由文本/工具调用稳健地解析为强类型 Decision。

L2 防腐层：所有 LLM 原始输出必须先经过此层归一化，
才能进入系统内部。核心域模型只看到已校验/已标记的决策。
"""

from __future__ import annotations

import json
import re

from lca.contracts.action import ActionRegistryProtocol
from lca.contracts.decision import Decision, DelegationSpec, ToolCall
from lca.contracts.enums import ActionType
from lca.contracts.ids import new_id
from lca.contracts.protocols import DecisionParser
from lca.contracts.semantic_keys import ORIGINAL_ACTION_TYPE
from lca.contracts.state import AgentState

_PARSE_FAILURE_CONFIDENCE = 0.1
_DEFAULT_CONFIDENCE = 0.5


class SimpleDecisionParser(DecisionParser):
    """稳健 JSON 解析器：别名归一化 + Registry 校验 + 失败兜底。

    当提供 ActionRegistry 时，解析器会校验 action_type 是否已注册；
    未注册的 action_type 不会被强行改写，而是在 extra 中标记原始值，
    交由韧性层（FallbackActionPolicy）决定降级策略。
    """

    def __init__(self, action_registry: ActionRegistryProtocol | None = None) -> None:
        self._action_registry = action_registry

    def parse(self, raw_output: str, state: AgentState) -> Decision:
        json_str = self._extract_json(raw_output)
        try:
            data = json.loads(json_str)
        except (json.JSONDecodeError, ValueError):
            return Decision(
                decision_id=new_id("dec"),
                action_type=ActionType.RESPOND,
                response_text=raw_output,
                rationale="解析失败兜底",
                confidence=_PARSE_FAILURE_CONFIDENCE,
            )

        raw_action = str(data.get("action_type", "respond")).lower().strip()
        action_type = (
            self._action_registry.normalize_alias(raw_action)
            if self._action_registry is not None
            else raw_action
        )

        extra: dict[str, str] = {}
        if self._action_registry is not None and not self._action_registry.is_registered(
            action_type
        ):
            extra[ORIGINAL_ACTION_TYPE] = action_type

        tool_calls: list[ToolCall] = []
        if action_type == ActionType.USE_TOOL:
            tool_name = data.get("tool_name") or data.get("tool")
            arguments = data.get("arguments") or data.get("args") or data.get("parameters") or {}
            if not isinstance(arguments, dict):
                arguments = {"expression": str(arguments)}
            if tool_name:
                tool_calls.append(
                    ToolCall(
                        call_id=new_id("call"),
                        tool_name=tool_name,
                        arguments=arguments,
                    )
                )
            else:
                action_type = ActionType.RESPOND

        delegate_to: DelegationSpec | None = None
        if action_type in (ActionType.DELEGATE, ActionType.HANDOFF):
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

        return Decision(
            decision_id=new_id("dec"),
            action_type=action_type,
            tool_calls=tool_calls,
            delegate_to=delegate_to,
            response_text=data.get("response_text") or data.get("response") or data.get("text"),
            rationale=data.get("rationale", ""),
            confidence=float(data.get("confidence", _DEFAULT_CONFIDENCE)),
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
