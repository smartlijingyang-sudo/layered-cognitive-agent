"""phase.concept.act_subgraph.act_join — typed receipt join boundary.

``concept.act_subgraph`` 内嵌节点:``list[EffectReceipt]`` →
``EffectReceipt`` + ``RoutingDecision``。

PR-3.8.5:1:1 only wiring。``[receipt]`` → ``receipt`` + 路由 ``act.observe``;
空列表 → 空 ``NodeOutput``;``len(receipts) > 1`` → 拒绝路由
``terminal.commit``,``receipt`` 端口不发射(fail-loud)。N:N partial-failure
domain 留后续 PR。

``RoutingDecision.next_node`` 直接落到拓扑下一节点(``act.observe`` 或
``terminal.commit``);``next_hint`` 携带语义原因(``join_1to1`` /
``join_rejects_parallel_in_v1``)供 bundle edge predicate 与 observability
消费。bundle edge 在 ``act.dispatch → act.join → act.observe`` 路径上
以 ``routing.next_hint == "join_1to1"`` 闸门 1:1 路径(参考 fanout PR-3.8.4
同模式)。

ADR-0219 §5.5 typed-port contract:``declared_inputs`` /
``declared_outputs`` 是编译期闭集;此节点只读 ``receipts``,写 ``receipt``
/ ``routing``,不触碰 Body / Registry / SafeExecutor。AGENTS.md §3 C10:
execution narrow door 仍由 ``effect.execute → Body → SafeExecutor →
Sandbox`` 持有,join 仅为 topology 适配 + 列表归约,不改语义、不执行。
"""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.act.effect_receipt import EffectReceipt
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
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
class ActJoinExecutor:
    """``concept.act.join`` 节点:1:1 receipt join (typed boundary)。

    ``receipts`` 列表归约为单一 ``receipt`` 端口;长度 0 → 空输出;
    长度 1 → 透传 + ``join_1to1`` 路由;长度 >1 → 拒绝路由
    ``terminal.commit`` 并空输出(N:N partial-failure policy 是 follow-up PR)。
    无副作用;不调用 Body / Registry / SafeExecutor;不构造 receipt;
    不读取 capability / budget / time。
    """

    semantic_name: str = "act.join"
    region: str = "act"
    declared_inputs: tuple[PortName, ...] = ("receipts",)
    declared_outputs: tuple[PortName, ...] = ("receipt", "routing")

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """act.join 入口。

        inputs 端口(yaml): receipts (list[EffectReceipt])
        outputs 端口(yaml): receipt (EffectReceipt), routing (RoutingDecision)
        """
        del context  # unused: pure function of input port value
        receipts_value = input.port_values.get("receipts")
        if receipts_value is None:
            receipts: list[EffectReceipt] = []
        elif isinstance(receipts_value, list):
            for index, item in enumerate(receipts_value):
                if not isinstance(item, EffectReceipt):
                    raise TypeError(
                        "act.join: 'receipts' port must be a list of "
                        f"EffectReceipt instances (item {index} is "
                        f"{type(item).__name__})"
                    )
            receipts = receipts_value
        else:
            raise TypeError(
                "act.join: 'receipts' port must be a list of EffectReceipt "
                f"instances or None, got {type(receipts_value).__name__}"
            )

        if len(receipts) == 0:
            return NodeOutput(port_values={})
        if len(receipts) == 1:
            return NodeOutput(
                port_values={
                    "receipt": receipts[0],
                    "routing": RoutingDecision(
                        action_type=ActionType.USE_TOOL,
                        next_node="act.observe",
                        next_hint="join_1to1",
                    ),
                }
            )

        return NodeOutput(
            port_values={
                "routing": RoutingDecision(
                    action_type=ActionType.USE_TOOL,
                    next_node="terminal.commit",
                    next_hint="join_rejects_parallel_in_v1",
                ),
            }
        )


@plugin(
    id="phase.concept.act_subgraph.act_join",
    Config=None,
    provides=("act::act.join",),
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
                "phase_concept_act_subgraph_act_join.checked",
                "phase_concept_act_subgraph_act_join.served",
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
    executor = ActJoinExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["ActJoinExecutor", "setup"]
