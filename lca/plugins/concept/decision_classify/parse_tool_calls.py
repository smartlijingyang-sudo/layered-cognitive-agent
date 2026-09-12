"""phase.concept.decision_classify.decision_parse_response — typed response parse.

concept.decision.classify 图节点 1(ADR-0221,合并 ADR-0220 §3.3 的
``decision.parse.tool_calls`` + ``decision.parse.intent``):typed
``LLMResponse`` → ``tuple[ToolCall, ...]`` + ``tuple[DelegationSpec, ...]`` +
``str``(intent 文本)。

节点职责:对同一 ``LLMResponse`` 做两路解析,合并成一个 pass:

1. native ``NativeToolCall`` 列表 → typed ``ToolCall`` 列表;``delegate``
   工具名过滤到 ``DelegationSpec`` 列表
2. leak recovery(``recover_leaked_tool_calls`` 解析 LLM 在 text 里
   偷偷放的 function-call JSON),把剥离后的剩余文本作为 ``intent``

失败 / 无调用 → 返回空 tuple + 空 intent,不静默降级到 RESPOND
—— 下游 ``decision.compose.action`` 显式拿三路入参组装,语义边界清晰。

合并动机:原 3 节点图的 fan-out 隐式假设与 v2 graph driver 单 cursor
脱节;``PlanInterpreter.run`` / ``PlanTraversal.advance`` 不支持 fan-out,
导致 ``decision.parse.intent`` 与 ``decision.compose.action`` 节点永远
不会被调度(见 run_dfa3f8615ea6 trace)。
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
class DecisionParseResponseExecutor:
    """concept.decision.classify 节点 1(合并后):LLMResponse → tool_calls + delegations + intent。"""

    semantic_name: str = "decision.parse.response"
    region: str = "concept"
    declared_inputs: tuple[PortName, ...] = ("response",)
    declared_outputs: tuple[PortName, ...] = ("tool_calls", "delegations", "intent")

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """decision.parse.response 入口。

        inputs 端口(yaml): response (LLMResponse)
        outputs 端口(yaml): tool_calls (tuple[ToolCall, ...]),
        delegations (tuple[DelegationSpec, ...]), intent (str)
        """
        del context
        response = input.port_values.get("response")
        if not isinstance(response, LLMResponse):
            raise TypeError(
                "decision.parse.response: 'response' port must be an LLMResponse, "
                f"got {type(response).__name__}"
            )

        tool_calls, delegations, intent = _parse_response(response)
        return NodeOutput(
            port_values={
                "tool_calls": tool_calls,
                "delegations": delegations,
                "intent": intent,
            }
        )


def _parse_response(
    response: LLMResponse,
) -> tuple[tuple[ToolCall, ...], tuple[Any, ...], str]:
    """Project native tool calls + extract intent from a single ``LLMResponse``.

    Leak recovery must run BEFORE intent extraction: ``recover_leaked_tool_calls``
    returns a new tuple ``(leftover, recovered)`` without mutating ``response.text``,
    so ``intent`` is computed from the post-recovery ``leftover`` (otherwise leaked
    JSON would be double-counted as intent text).
    """
    from lca.cognition.brain.prompt.leaked_tool_call import recover_leaked_tool_calls
    from lca.contracts.models.core.execution.decision import DelegationSpec

    leftover = (response.text or "").strip()
    native_calls = list(response.tool_calls or ())
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
    return tuple(tool_calls), tuple(delegations), leftover


@plugin(
    id="phase.concept.decision_classify.decision_parse_response",
    Config=None,
    provides=("concept::decision.parse.response",),
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
                "phase_concept_decision_classify_decision_parse_response.checked",
                "phase_concept_decision_classify_decision_parse_response.served",
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
    executor = DecisionParseResponseExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["DecisionParseResponseExecutor", "setup"]
