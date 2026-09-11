"""phase.concept.decision_classify.decision_parse_tool_calls — typed tool-call parse.

concept.decision.classify 图节点 1:typed ``LLMResponse`` →
``tuple[ToolCall, ...]``(ADR-0220 §3.3)。

节点职责:把原生 ``NativeToolCall`` 列表投影成 ``ToolCall`` typed 列表,
附带 leak recovery(``recover_leaked_tool_calls`` 解析 LLM 在 text 里
偷偷放的 function-call JSON)。失败 / 无调用 → 返回空 tuple,不静默
降级到 RESPOND —— 下游 ``decision.compose.action`` 显式拿空 tuple +
intent 文本组装,语义边界清晰。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.core.conversation.llm import LLMResponse
from lca.contracts.models.core.execution.decision import ToolCall
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_1.ports import PortName
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin

_DELEGATE_TOOL_NAME = "delegate"


@dataclass(frozen=True, slots=True)
class DecisionParseToolCallsExecutor:
    """concept.decision.classify 节点 1:LLMResponse → tuple[ToolCall, ...]。"""

    semantic_name: str = "decision.parse.tool_calls"
    region: str = "concept"
    declared_inputs: tuple[PortName, ...] = ("response",)
    declared_outputs: tuple[PortName, ...] = ("tool_calls", "delegations")

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """decision.parse.tool_calls 入口。

        inputs 端口(yaml):response (LLMResponse)
        outputs 端口(yaml):tool_calls (tuple[ToolCall, ...]),
        delegations (tuple[DelegationSpec, ...])
        """
        import logging

        _log = logging.getLogger(__name__)
        response = input.port_values.get("response")
        _log.info(
            "decision.parse.tool_calls response_type=%s text_len=%s tool_calls_count=%s",
            type(response).__name__ if response is not None else "None",
            len(response.text) if isinstance(response, LLMResponse) and getattr(response, "text", None) else 0,
            len(response.tool_calls) if isinstance(response, LLMResponse) and getattr(response, "tool_calls", None) else 0,
        )
        if not isinstance(response, LLMResponse):
            raise TypeError(
                "decision.parse.tool_calls: 'response' port must be an LLMResponse, "
                f"got {type(response).__name__}"
            )

        tool_calls, delegations = _parse(response)
        _log.info(
            "decision.parse.tool_calls parsed tool_calls=%d delegations=%d",
            len(tool_calls),
            len(delegations),
        )
        return NodeOutput(
            port_values={
                "tool_calls": tool_calls,
                "delegations": delegations,
            }
        )


def _parse(
    response: LLMResponse,
) -> tuple[tuple[ToolCall, ...], tuple[Any, ...]]:
    """Project native tool calls onto typed ToolCall + DelegationSpec tuple pair.

    Delegates are filtered out of the tool_calls tuple so the action composer
    can branch on DELEGATE vs USE_TOOL cleanly.
    """
    from lca.cognition.brain.prompt.leaked_tool_call import recover_leaked_tool_calls
    from lca.contracts.models.core.execution.decision import DelegationSpec

    native_calls = list(response.tool_calls)
    leftover = (response.text or "").strip()
    if not native_calls and leftover:
        leftover, recovered = recover_leaked_tool_calls(leftover)
        native_calls = recovered

    delegations: list[DelegationSpec] = []
    tool_calls: list[ToolCall] = []
    for tc in native_calls:
        if tc.name == _DELEGATE_TOOL_NAME:
            delegations.append(
                DelegationSpec(
                    subtask=str(tc.arguments.get("subtask", "")),
                    target_role=tc.arguments.get("target_role") or None,
                    target_agent_id=tc.arguments.get("target_agent_id") or None,
                )
            )
            continue
        tool_calls.append(
            ToolCall(
                call_id=tc.call_id or new_id("call"),
                tool_name=tc.name,
                arguments=dict(tc.arguments),
            )
        )
    return tuple(tool_calls), tuple(delegations)


@plugin(
    id="phase.concept.decision_classify.decision_parse_tool_calls",
    Config=None,
    provides=("concept::decision.parse.tool_calls",),
    requires=(),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "phase_concept_decision_classify_decision_parse_tool_calls.checked",
                "phase_concept_decision_classify_decision_parse_tool_calls.served",
            )
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config=None) -> None:
    """Composite-key 注册:``{region}::{semantic_name}``。"""
    del config
    executor = DecisionParseToolCallsExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["DecisionParseToolCallsExecutor", "setup"]
