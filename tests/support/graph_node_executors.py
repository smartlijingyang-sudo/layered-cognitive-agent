"""Explicit default graph-node primitive closure for strategy unit tests."""

from __future__ import annotations

from lca.contracts.models.team.graph import NodeType
from lca.plugins.phase_graph.agent import AgentGraphNodeExecutor
from lca.plugins.phase_graph.aggregator import AggregatorGraphNodeExecutor
from lca.plugins.phase_graph.registry import GraphNodeExecutorRegistry
from lca.plugins.phase_graph.topology import TopologyGraphNodeExecutor


def build_default_graph_node_executor_registry() -> GraphNodeExecutorRegistry:
    """Create the same complete node primitive set declared by web-app.yaml."""

    registry = GraphNodeExecutorRegistry()
    registry.register(NodeType.AGENT, AgentGraphNodeExecutor())
    registry.register(NodeType.AGGREGATOR, AggregatorGraphNodeExecutor())
    for node_type in (NodeType.ENTRY, NodeType.EXIT, NodeType.ROUTER):
        registry.register(node_type, TopologyGraphNodeExecutor(node_type))
    return registry


__all__ = ["build_default_graph_node_executor_registry"]
