"""LobeHub ``llm_result`` phase — classify one LLMResponse into a Decision.

Mirrors ``GeneralChatAgent`` ``llm_result`` + ``callLlmFinalizer``:
- resolved tool_calls → USE_TOOL / DELEGATE
- text only → RESPOND
- empty → parse-failure RESPOND
"""

from __future__ import annotations

from lca.contracts.atoms.enums import ActionType
from lca.contracts.atoms.ids import new_id
from lca.contracts.models.core.decision import Decision, DelegationSpec, ToolCall
from lca.contracts.models.core.llm import LLMResponse

_PARSE_FAILURE_USER_MESSAGE = "抱歉，模型未返回有效决策，请重试。"
_DELEGATE_TOOL_NAME = "delegate"


def build_decision_from_response(response: LLMResponse) -> Decision:
    """Map native function-calling output to LCA Decision (LobeHub tool wire parity)."""
    if response.tool_calls:
        delegates = [tc for tc in response.tool_calls if tc.name == _DELEGATE_TOOL_NAME]
        if delegates:
            specs = [
                DelegationSpec(
                    subtask=tc.arguments.get("subtask", ""),
                    target_role=tc.arguments.get("target_role") or None,
                    target_agent_id=tc.arguments.get("target_agent_id") or None,
                )
                for tc in delegates
            ]
            return Decision(
                decision_id=new_id("dec"),
                action_type=ActionType.DELEGATE.value,
                rationale="",
                confidence=1.0,
                delegations=specs,
            )
        tool_calls = [
            ToolCall(
                call_id=tc.call_id or new_id("call"),
                tool_name=tc.name,
                arguments=tc.arguments,
            )
            for tc in response.tool_calls
        ]
        return Decision(
            decision_id=new_id("dec"),
            action_type=ActionType.USE_TOOL.value,
            rationale="",
            confidence=1.0,
            tool_calls=tool_calls,
        )
    text = (response.text or "").strip()
    if text:
        return Decision(
            decision_id=new_id("dec"),
            action_type=ActionType.RESPOND.value,
            rationale="",
            confidence=1.0,
            response_text=text,
        )
    return Decision(
        decision_id=new_id("dec"),
        action_type=ActionType.RESPOND.value,
        rationale="模型返回空响应",
        confidence=0.0,
        response_text=_PARSE_FAILURE_USER_MESSAGE,
    )


def has_resolved_tool_calls(response: LLMResponse) -> bool:
    """Whether ``llm_result`` would execute tools (non-delegate tool_calls present)."""
    if not response.tool_calls:
        return False
    return any(tc.name != _DELEGATE_TOOL_NAME for tc in response.tool_calls)
