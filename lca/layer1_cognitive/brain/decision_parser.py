"""DecisionParser —— 将自由文本/工具调用稳健地解析为强类型 Decision。

防腐层：所有 LLM 原始输出必须先经过此层归一化，才能进入系统内部。
归一化管线（ADR-0045）::

    JSON 提取 → 意图形状归一 → 别名归一化 → 词表校验 → 越界降级

下游永远只看到词表内的 action_type 与规范字段位置——越界决策在解析期就被
改写，而不是留到执行期以异常形式暴露。
"""

from __future__ import annotations

import json
import re
from typing import Any

from lca.contracts.atoms.enums import ActionType
from lca.contracts.atoms.ids import new_id
from lca.contracts.atoms.semantic_keys import (
    TOOL_WIRE_FINISH_REASON,
    TOOL_WIRE_INCOMPLETE,
    TOOL_WIRE_INVALID,
    TOOL_WIRE_RAW_PREVIEW,
    TOOL_WIRE_REASON,
    TOOL_WIRE_STATUS,
)
from lca.contracts.models.core.decision import Decision, DelegationSpec, ToolCall
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols import DecisionParser, DegradationPolicy
from lca.contracts.protocols.action import ActionRegistryProtocol
from lca.layer1_cognitive.brain.decision_shape import normalize_intent_shape
from lca.layer1_cognitive.brain.degradation import GracefulDegradation

_PARSE_FAILURE_CONFIDENCE = 0.1
_DEFAULT_CONFIDENCE = 0.5
_TOOL_WIRE_EXTRA_KEYS: tuple[str, ...] = (
    TOOL_WIRE_STATUS,
    TOOL_WIRE_REASON,
    TOOL_WIRE_RAW_PREVIEW,
    TOOL_WIRE_FINISH_REASON,
    "tool_wire_detail",
)
_BLOCKING_WIRE_STATUSES: frozenset[str] = frozenset({TOOL_WIRE_INCOMPLETE, TOOL_WIRE_INVALID})


def extract_json_block(raw_output: str) -> str:
    """从 LLM 原始输出提取 JSON 文本：优先 ```json 围栏，其次裸 {...} 块。

    归一化管线的公共第一步；DecisionParser 与 L4 自动组队
    （LLMTeamCaster）共用，禁止各自复制提取逻辑。
    """
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", raw_output, re.DOTALL)
    if m:
        return m.group(1).strip()
    m = re.search(r"\{.*\}", raw_output, re.DOTALL)
    if m:
        return m.group(0)
    return raw_output.strip()


class SimpleDecisionParser(DecisionParser):
    """稳健 JSON 解析器：形状归一 + 别名 + 词表校验 + 越界降级 + 解析兜底。

    注入 ActionRegistry 后，解析结果保证词表内：未注册的 action_type
    交由 DegradationPolicy 改写（默认 GracefulDegradation）；无法降级时
    原样保留，由 Body 以 UnregisteredActionError 拒绝。
    未注入 ActionRegistry 时跳过校验与降级，仍执行意图形状归一。
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

        if not isinstance(data, dict):
            return Decision(
                decision_id=new_id("dec"),
                action_type=ActionType.RESPOND,
                response_text=raw_output,
                rationale="解析失败兜底：根节点非对象",
                confidence=_PARSE_FAILURE_CONFIDENCE,
            )

        registry = self._action_registry
        shaped = normalize_intent_shape(
            data,
            resolve_alias=(registry.normalize_alias if registry is not None else None),
            is_registered=(registry.is_registered if registry is not None else None),
        )

        raw_action = str(shaped.get("action_type", ActionType.RESPOND.value)).lower().strip()
        if registry is not None:
            aliased = registry.normalize_alias(raw_action)
            # str(ActionType.X) → 'ActionType.X'；规范名必须取 .value
            action_type = (
                (aliased.value if isinstance(aliased, ActionType) else str(aliased)).lower().strip()
            )
        else:
            action_type = raw_action

        # 工具意图：仅当仍为 use_tool（且仍有真实 tool_name）时保留 tool_calls
        tool_name = shaped.get("tool_name") or shaped.get("tool")
        arguments = shaped.get("arguments") or shaped.get("args") or shaped.get("parameters") or {}
        if not isinstance(arguments, dict):
            arguments = {}
        wire_extra = self._extract_tool_wire_extra(shaped)
        wire_status = str(wire_extra.get(TOOL_WIRE_STATUS) or "")
        # incomplete/invalid：清空 arguments，禁止把半截 code 当可执行载荷
        if wire_status in _BLOCKING_WIRE_STATUSES:
            arguments = {}
        tool_calls: list[ToolCall] = []
        # 有 tool_name 即构造 tool_calls：供 use_tool 执行，也为越界 action
        # （如 compute）经 GracefulDegradation 降级为 use_tool 提供内容证据
        if tool_name:
            tool_calls.append(
                ToolCall(
                    call_id=new_id("call"),
                    tool_name=str(tool_name),
                    arguments=arguments,
                )
            )
        elif action_type == ActionType.USE_TOOL.value:
            action_type = ActionType.RESPOND.value

        delegations: list[DelegationSpec] = []
        if action_type in (ActionType.DELEGATE.value, ActionType.HANDOFF.value):
            delegations = self._parse_delegations(shaped)

        shape_degraded = shaped.get("_shape_degraded_from")
        degraded_from = str(shape_degraded) if shape_degraded else None

        decision = Decision(
            decision_id=new_id("dec"),
            action_type=action_type,
            tool_calls=tool_calls,
            delegations=delegations,
            response_text=self._coalesce_response_text(shaped),
            rationale=str(shaped.get("rationale") or ""),
            confidence=self._coerce_confidence(shaped.get("confidence", _DEFAULT_CONFIDENCE)),
            degraded_from=degraded_from,
            extra=wire_extra,
        )
        return self._degrade_if_unregistered(decision)

    @staticmethod
    def _extract_tool_wire_extra(data: dict[str, Any]) -> dict[str, Any]:
        """把 adapter 编码的 tool_wire_* 顶层键迁入 Decision.extra。"""
        out: dict[str, Any] = {}
        for key in _TOOL_WIRE_EXTRA_KEYS:
            if key in data and data[key] is not None:
                out[key] = data[key]
        return out

    def _degrade_if_unregistered(self, decision: Decision) -> Decision:
        """词表归一化最后一道：越界 action_type 就地降级为词表内等价行动。"""
        registry = self._action_registry
        if registry is None or registry.is_registered(decision.action_type):
            return decision
        return self._degradation.degrade(decision, registry)

    @staticmethod
    def _coalesce_response_text(data: dict[str, Any]) -> str | None:
        for key in ("response_text", "response", "text"):
            value = data.get(key)
            if isinstance(value, str):
                return value
        return None

    @staticmethod
    def _coerce_confidence(raw: object) -> float:
        try:
            return float(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return _DEFAULT_CONFIDENCE

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
        return extract_json_block(text)
