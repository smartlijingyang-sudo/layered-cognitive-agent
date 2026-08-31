"""No-op topology primitives for entry, exit, and router graph nodes."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.capabilities import GRAPH_NODE_EXECUTORS
from lca.contracts.models.team.graph import NodeType
from lca.contracts.protocols.collaboration.graph_node_executor import (
    GraphNodeExecutionContext,
    GraphNodeExecutor,
)
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress


class Config(BaseModel):
    """The topology primitives have no configuration."""

    model_config = {"extra": "forbid"}


class TopologyGraphNodeExecutor(GraphNodeExecutor):
    """Represent a graph topology marker with no local execution behavior."""

    is_aggregator = False

    def __init__(self, node_type: NodeType) -> None:
        if node_type not in {NodeType.ENTRY, NodeType.EXIT, NodeType.ROUTER}:
            raise ValueError(f"TopologyGraphNodeExecutor does not support {node_type.value!r}")
        self.node_type = node_type

    async def execute(self, context: GraphNodeExecutionContext) -> None:
        """Preserve the declared topology marker without emitting a result."""

        del context
        return None


@plugin(
    id="graph-node.topology.default",
    Config=Config,
    provides=[],
    requires=[GRAPH_NODE_EXECUTORS.key],
    implements=[GraphNodeExecutor],
    layer="L3",
    kind=PluginKind.PRIMITIVE,
    effects=EffectClass.NONE,
    description="Register default no-op primitives for graph entry, exit, and router nodes.",
    test_suite="tests/test_graph_node_executors.py",


    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G7_EXECUTION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=('plugin.serve',),
        evidence=('graph-node_topology_default.checked', 'graph-node_topology_default.served'),
        revision="v1",
    ),
    relations=(),

    ownership=OwnershipDeclaration(
        reads=('plugin.serve',),
        emits=('plugin.served',),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Contribute all topology-marker primitives to the selected registry."""

    del config
    registry = ctx.require(GRAPH_NODE_EXECUTORS.key)
    for node_type in (NodeType.ENTRY, NodeType.EXIT, NodeType.ROUTER):
        registry.register(node_type, TopologyGraphNodeExecutor(node_type))


__all__ = ["Config", "TopologyGraphNodeExecutor", "setup"]
