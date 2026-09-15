"""phase.concept.action_turn.act_action_resolve — typed action resolver.

agent.action.turn 内嵌节点 1 (``concept.action.turn``):typed
``Decision`` → ``Decision`` (no-op projection, owned by this concept
graph because ADR-0220 §3.4 names it as a business-graph node).

``act.action.resolve`` 的语义在 P5/P6 已经在 ``concept.decision.classify``
+ ``concept.decision.enforce`` 两图完成(P6 切掉 think.classify +
think.gate)。这里把它在 ``agent.action.turn`` 视作 typed projection:
入参 Decision 已经过 enforce,出参直接透传,占位 ``resolve`` 节点。
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
from lca.contracts.models.core.execution.decision import Decision
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


@dataclass(frozen=True, slots=True)
class ActActionResolveExecutor:
    """``concept.action.turn`` 节点 1:Decision → Decision(passthrough)。"""

    semantic_name: str = "act.action.resolve"
    region: str = "concept"
    declared_inputs: tuple[PortName, ...] = ("decision",)
    declared_outputs: tuple[PortName, ...] = ("decision",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """act.action.resolve 入口。

        inputs 端口(yaml):decision (Decision)
        outputs 端口(yaml):decision (Decision)
        """
        del context
        decision = input.port_values.get("decision")
        if not isinstance(decision, Decision):
            raise TypeError(
                "act.action.resolve: 'decision' port must be a Decision "
                f"instance, got {type(decision).__name__}"
            )
        return NodeOutput(port_values={"decision": decision})


@plugin(
    id="phase.concept.action_turn.act_action_resolve",
    Config=None,
    provides=("concept::act.action.resolve",),
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
                "phase_concept_action_turn_act_action_resolve.checked",
                "phase_concept_action_turn_act_action_resolve.served",
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
    executor = ActActionResolveExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["ActActionResolveExecutor", "setup"]
