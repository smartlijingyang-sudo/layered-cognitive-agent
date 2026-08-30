"""Profile-selectable collaboration graph-node primitives."""

from lca.plugins.graph_nodes.agent import AgentGraphNodeExecutor
from lca.plugins.graph_nodes.aggregator import AggregatorGraphNodeExecutor
from lca.plugins.graph_nodes.registry import GraphNodeExecutorRegistry
from lca.plugins.graph_nodes.topology import TopologyGraphNodeExecutor

__all__ = [
    "AgentGraphNodeExecutor",
    "AggregatorGraphNodeExecutor",
    "GraphNodeExecutorRegistry",
    "TopologyGraphNodeExecutor",
]
