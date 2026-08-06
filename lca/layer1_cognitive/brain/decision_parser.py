"""DecisionParser —— 将自由文本/工具调用稳健地解析为强类型 Decision。

防腐层：所有 LLM 原始输出必须先经过此层归一化，才能进入系统内部。
归一化管线：JSON 提取 → 别名归一化 → 词表校验 → 越界降级（GracefulDegradation）。
下游永远只看到词表内的 action_type——越界决策在解析期就被改写，
而不是留到执行期以异常形式暴露。
"""

from __future__ import annotations

import json
import re
from typing import Any

from lca.contracts.atoms.enums import ActionType
from lca.contracts.atoms.ids import new_id
from lca.contracts.models.core.decision import Decision, DelegationSpec, ToolCall
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols import DecisionParser, DegradationPolicy
from lca.contracts.protocols.action import ActionRegistryProtocol
from lca.layer1_cognitive.brain.degradation import GracefulDegradation

_PARSE_FAILURE_CONFIDENCE = 0.1
_DEFAULT_CONFIDENCE = 0.5


class SimpleDecisionParser(DecisionParser):
    """稳健 JSON 解析器：别名归一化 + 词表校验 + 越界降级 + 解析兜底。

    注入 ActionRegistry 后，解析结果保证词表内：未注册的 action_type
    交由 DegradationPolicy 改写（默认 GracefulDegradation）；无法降级时
    原样保留，由 Body 以 UnregisteredActionError 拒绝。
    未注入 ActionRegistry 时跳过校验与降级。
    """

    def __init__(
        self,
        action_registry: ActionRegistryProtocol | None = None,
        degradation: DegradationPolicy | None = None,
    ) -> None:
        self._action_registry = action_registry
        self._degradation = degradation if degradation is not None else GracefulDegradation()

    def parse(self, raw_output: str, state: AgentState) -> Decision:
        del state
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

        # 工具意图与 action_type 解耦提取：LLM 可能把工具调用挂在越界的
        # action_type 上，内容先收齐，交给降级策略决定是否改写。
        tool_name = data.get("tool_name") or data.get("tool")
        arguments = data.get("arguments") or data.get("args") or data.get("parameters") or {}
        if not isinstance(arguments, dict):
            arguments = {}
        tool_calls: list[ToolCall] = []
        if tool_name:
            tool_calls.append(
                ToolCall(
                    call_id=new_id("call"),
                    tool_name=tool_name,
                    arguments=arguments,
                )
            )
        elif action_type == ActionType.USE_TOOL:
            action_type = ActionType.RESPOND

        delegations: list[DelegationSpec] = []
        if action_type in (ActionType.DELEGATE, ActionType.HANDOFF):
            delegations = self._parse_delegations(data)

        decision = Decision(
            decision_id=new_id("dec"),
            action_type=action_type,
            tool_calls=tool_calls,
            delegations=delegations,
            response_text=data.get("response_text") or data.get("response") or data.get("text"),
            rationale=data.get("rationale", ""),
            confidence=float(data.get("confidence", _DEFAULT_CONFIDENCE)),
        )
        return self._degrade_if_unregistered(decision)

    def _degrade_if_unregistered(self, decision: Decision) -> Decision:
        """词表归一化最后一道：越界 action_type 就地降级为词表内等价行动。"""
        registry = self._action_registry
        if registry is None or registry.is_registered(decision.action_type):
            return decision
        return self._degradation.degrade(decision, registry)

    @staticmethod
    def _parse_delegations(data: dict[str, Any]) -> list[DelegationSpec]:
        """Normalize LLM JSON into Decision.delegations only.

        Accepted JSON shapes:
        - ``delegations`` list of objects (preferred multi-target form)
        - flat single: target_role + subtask (+ optional context_refs)
        """
        multi = data.get("delegations")
        if isinstance(multi, list) and multi:
            out: list[DelegationSpec] = []
            for item in multi:
                if not isinstance(item, dict):
                    continue
                refs = item.get("context_refs") or item.get("context") or []
                if not isinstance(refs, list):
                    refs = [str(refs)]
                out.append(
                    DelegationSpec(
                        subtask=str(item.get("subtask", "")),
                        target_role=item.get("target_role"),
                        context_refs=refs,
                    )
                )
            return out

        subtask = data.get("subtask", "")
        target_role = data.get("target_role")
        context_refs = data.get("context_refs") or data.get("context") or []
        if not isinstance(context_refs, list):
            context_refs = [str(context_refs)]
        # Single-target flat form always yields one entry when any target signal exists
        # or subtask is present (existing parser behavior for handoff/delegate).
        if target_role is not None or subtask or context_refs:
            return [
                DelegationSpec(
                    subtask=str(subtask),
                    target_role=target_role,
                    context_refs=context_refs,
                )
            ]
        return []

    @staticmethod
    def _extract_json(text: str) -> str:
        m = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
        if m:
            return m.group(1).strip()
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return m.group(0)
        return text.strip()
