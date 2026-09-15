"""phase.think.decision_parse.decision_parse — typed LLMResponse → Decision boundary.

think.decision.parse 图节点 1:从 ``LLMResponse`` 投影 typed
``Decision``,spec §E 单一职责节点。
"""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
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
from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_1.ports import PortName
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.framework.graph.nodes.decision_parse import decision_parse
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


@dataclass(frozen=True, slots=True)
class DecisionParseExecutor:
    """think.decision.parse 节点 1:(state, llm_response) → Decision。"""

    semantic_name: str = "decision.parse"
    region: str = "think"
    declared_inputs: tuple[PortName, ...] = ("state", "llm_response")
    declared_outputs: tuple[PortName, ...] = ("decision",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """decision.parse 入口。

        inputs 端口(yaml):state (AgentState), llm_response (LLMResponse)
        outputs 端口(yaml):decision (Decision)

        state 缺失时回退 ``context.runtime``(与 history_assemble /
        context_compose 一致);llm_response 缺失或类型不匹配 → TypeError。
        """
        state = input.port_values.get("state")
        if state is None:
            state = context.runtime.get("state") if hasattr(context, "runtime") else None
        if state is not None and not isinstance(state, AgentState):
            raise TypeError(
                "decision.parse: 'state' port must be an AgentState "
                f"instance, got {type(state).__name__}"
            )
        llm_response = input.port_values.get("llm_response")
        if not isinstance(llm_response, LLMResponse):
            raise TypeError(
                "decision.parse: 'llm_response' port must be an LLMResponse, "
                f"got {type(llm_response).__name__}"
            )
        result: Decision = await decision_parse(state=state, llm_response=llm_response)
        return NodeOutput(port_values={"decision": result})


@plugin(
    id="phase.think.decision_parse.decision_parse",
    Config=None,
    provides=("think::decision.parse",),
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
                "phase_think_decision_parse_decision_parse.checked",
                "phase_think_decision_parse_decision_parse.served",
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
    executor = DecisionParseExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["DecisionParseExecutor", "setup"]
