"""phase.concept.act_subgraph.act_fanout — typed envelope fan-out boundary.

``concept.act_subgraph`` 内嵌节点:``CommandEnvelope`` →
``list[CommandEnvelope]`` + ``RoutingDecision``。

PR-3.8.4:1:1 only wiring。envelope → ``[envelope]``;空 envelope →
``[]``。N:N fanout 与 partial-failure domain 留后续 PR。

``declared_outputs`` 显式包含 ``envelope`` 作为 1:1 pass-through:当下游
``act.dispatch`` 仍按 ``envelope`` 单值消费时,fanout 透传原 envelope 以
保证 runtime wiring 在 1:1 路径上不断;``envelopes`` 列表语义为后续 N:N
PR 预留(N:N PR 会让 dispatch 改为消费 ``envelopes``)。

ADR-0219 §5.5 typed-port contract:``declared_inputs`` /
``declared_outputs`` 是编译期闭集;此节点只读 ``envelope``,写
``envelope`` / ``envelopes`` / ``routing``,不触碰 Body / Registry /
SafeExecutor。AGENTS.md §3 C10:execution narrow door 仍由
``effect.execute → Body → SafeExecutor → Sandbox`` 持有,fanout 仅为
topology 适配,不改语义。
"""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.enums.enums import ActionType
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
from lca.contracts.protocols.act.command.envelope import CommandEnvelope
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_1.ports import PortName
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.protocols.graph.routing import RoutingDecision
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


@dataclass(frozen=True, slots=True)
class ActFanoutExecutor:
    """``concept.act.fanout`` 节点:1:1 envelope fan-out (typed boundary)。

    envelope → [envelope];None → []。无副作用;不调用 Body / Registry /
    SafeExecutor;不构造 envelope;不读取 capability / budget / time。
    """

    semantic_name: str = "act.fanout"
    region: str = "concept"
    declared_inputs: tuple[PortName, ...] = ("envelope",)
    declared_outputs: tuple[PortName, ...] = ("envelope", "envelopes", "routing")

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """act.fanout 入口。

        inputs 端口(yaml): envelope (CommandEnvelope | None)
        outputs 端口(yaml): envelopes (list[CommandEnvelope]), routing (RoutingDecision)
        """
        del context  # unused: pure function of input port value
        envelope = input.port_values.get("envelope")
        if envelope is None:
            envelopes: list[CommandEnvelope] = []
            routing = RoutingDecision(
                action_type=ActionType.USE_TOOL,
                next_node="act.dispatch",
                next_hint="fanout_empty",
            )
        else:
            if not isinstance(envelope, CommandEnvelope):
                raise TypeError(
                    "act.fanout: 'envelope' port must be a CommandEnvelope "
                    f"instance or None, got {type(envelope).__name__}"
                )
            envelopes = [envelope]
            routing = RoutingDecision(
                action_type=ActionType.USE_TOOL,
                next_node="act.dispatch",
                next_hint="fanout_1to1",
            )
        return NodeOutput(
            port_values={"envelope": envelope, "envelopes": envelopes, "routing": routing}
        )


@plugin(
    id="phase.concept.act_subgraph.act_fanout",
    Config=None,
    provides=("concept::act.fanout",),
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
                "phase_concept_act_subgraph_act_fanout.checked",
                "phase_concept_act_subgraph_act_fanout.served",
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
    executor = ActFanoutExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["ActFanoutExecutor", "setup"]
