"""phase.think.route.decide — typed routing decision after shortcut.

think 子图节点 plugin:将 ``think.shortcut`` 输出的 ``decision`` 端口
转换为 ``RoutingDecision`` typed port,替代原先 bundle 图里两条
``when: { kind: missing | exists, port: decision }`` 边谓词。

路由逻辑从边 YAML(隐藏、不可测)移入节点代码(类型化、可测、可调试)。

ADR-0218 §3.3:节点 plugin 由作者显式书写完整 ``@plugin(...)`` 装饰器,
工厂 ``setup(ctx)`` 通过 Cordis ``ctx.provide`` 注册 composite key。
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
class ThinkRouteDecideExecutor:
    """think 节点:将 shortcut 的 decision 端口转为 RoutingDecision typed port。"""

    semantic_name: str = "think.route.decide"
    region: str = "think"
    declared_inputs: tuple[PortName, ...] = ("decision",)
    declared_outputs: tuple[PortName, ...] = ("routing",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """think 子图节点入口。

        inputs 端口(yaml): decision
        outputs 端口(yaml): routing
        """
        del context  # unused: pure function of input ports
        decision = input.port_values.get("decision")
        if decision is None:
            # No shortcut decision — fall through to full reasoning path.
            routing = RoutingDecision(
                action_type=ActionType.RESPOND,
                next_node="think.route",
            )
        else:
            # Shortcut produced a decision — skip reasoning, go to gate.
            routing = RoutingDecision(
                action_type=ActionType.SHORT_CIRCUIT,
                next_node="think.gate",
            )
        return NodeOutput(port_values={"routing": routing})


@plugin(
    id="phase.think.route.decide",
    Config=None,
    provides=("think::think.route.decide",),
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
                "phase_think_route_decide.checked",
                "phase_think_route_decide.served",
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
    executor = ThinkRouteDecideExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["ThinkRouteDecideExecutor", "setup"]
