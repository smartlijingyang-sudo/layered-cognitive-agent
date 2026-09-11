"""phase.concept.action_turn.act_capability_grant — typed capability grant.

business.action.turn 内嵌节点 2 (``concept.action.turn``):typed
``Decision`` → ``Decision`` (passthrough, capability grant seam 留待
后续 PR 接入 effect policy)。

ADR-0220 §3.4 ``act.capability.grant`` 是 business-graph 节点名。本节点
作为 concept.action.turn 内嵌 typed 投影 — 真正的 capability grant
(EffectPolicy / CapabilityGrant envelope) 留待 P10 收口。本 PR 内
``act.capability.grant`` 是 typed passthrough, 不读 state 也不调
capability seam。
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
class ActCapabilityGrantExecutor:
    """``concept.action.turn`` 节点 2:Decision → Decision(passthrough)。"""

    semantic_name: str = "act.capability.grant"
    region: str = "concept"
    declared_inputs: tuple[PortName, ...] = ("decision",)
    declared_outputs: tuple[PortName, ...] = ("decision",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """act.capability.grant 入口。

        inputs 端口(yaml):decision (Decision)
        outputs 端口(yaml):decision (Decision)
        """
        del context
        decision = input.port_values.get("decision")
        if not isinstance(decision, Decision):
            raise TypeError(
                "act.capability.grant: 'decision' port must be a Decision "
                f"instance, got {type(decision).__name__}"
            )
        return NodeOutput(port_values={"decision": decision})


@plugin(
    id="phase.concept.action_turn.act_capability_grant",
    Config=None,
    provides=("concept::act.capability.grant",),
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
                "phase_concept_action_turn_act_capability_grant.checked",
                "phase_concept_action_turn_act_capability_grant.served",
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
    executor = ActCapabilityGrantExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["ActCapabilityGrantExecutor", "setup"]
