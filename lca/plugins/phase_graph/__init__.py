"""Profile-selectable collaboration graph-node primitives."""

from lca.plugins.loop.graph.nodes.agent.plugin import AgentGraphNodeExecutor
from lca.plugins.loop.graph.nodes.aggregator.plugin import AggregatorGraphNodeExecutor
from lca.plugins.loop.graph.nodes.registry.plugin import GraphNodeExecutorRegistry
from lca.plugins.loop.graph.nodes.topology.plugin import TopologyGraphNodeExecutor

__all__ = [
    "AgentGraphNodeExecutor",
    "AggregatorGraphNodeExecutor",
    "GraphNodeExecutorRegistry",
    "TopologyGraphNodeExecutor",
]
