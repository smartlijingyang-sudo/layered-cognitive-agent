"""DecisionClassifier Provider plugin — Tier-2."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.enums import ActionType
from lca.contracts.atoms.ids import new_id
from lca.contracts.models.core.decision import Decision, DelegationSpec, ToolCall
from lca.contracts.models.core.llm import LLMResponse
from lca.contracts.protocols.decision_classifier import DecisionClassifier
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.layer1_cognitive.brain.leaked_tool_call import recover_leaked_tool_calls

_PARSE_FAILURE_USER_MESSAGE = "抱歉，模型未返回有效决策，请重试。"
_DELEGATE_TOOL_NAME = "delegate"


class Config(BaseModel):
    model_config = {"extra": "forbid"}


class DefaultDecisionClassifier(DecisionClassifier):
    """Default DecisionClassifier implementation.

    Migrated from lca/layer1_cognitive/brain/llm_result.py:build_decision_from_response().
    Maps native function-calling output to LCA Decision (LobeHub tool wire parity).
    """

    def classify(self, response: LLMResponse) -> Decision:
        """Map native function-calling output to LCA Decision (LobeHub tool wire parity)."""
        tool_calls = list(response.tool_calls)
        leftover = (response.text or "").strip()
        if not tool_calls and leftover:
            leftover, recovered = recover_leaked_tool_calls(leftover)
            tool_calls = recovered
        if tool_calls:
            delegates = [tc for tc in tool_calls if tc.name == _DELEGATE_TOOL_NAME]
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
            mapped = [
                ToolCall(
                    call_id=tc.call_id or new_id("call"),
                    tool_name=tc.name,
                    arguments=tc.arguments,
                )
                for tc in tool_calls
            ]
            return Decision(
                decision_id=new_id("dec"),
                action_type=ActionType.USE_TOOL.value,
                rationale="",
                confidence=1.0,
                tool_calls=mapped,
            )
        text = leftover
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


@plugin(
    id="lca-decision-classifier-provider",
    provides=["decision_classifier"],
    implements=[DecisionClassifier],
    layer="L1",
    effects="none",
    description="Provide the default DecisionClassifier implementation.",
    test_suite="tests/test_plugin_alignment.py::test_tier2_plugin_shape",
    kind=PluginKind.PROVIDER,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    ctx.provide("decision_classifier", DefaultDecisionClassifier())


__all__ = ["DefaultDecisionClassifier", "setup"]
