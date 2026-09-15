"""Explicit default graph-node primitive closure for strategy unit tests."""

from __future__ import annotations

from lca.contracts.models.team.graph.graph import NodeType
from lca.nodes.loop.agent.plugin import AgentGraphNodeExecutor
from lca.nodes.loop.aggregator.plugin import AggregatorGraphNodeExecutor
from lca.nodes.loop.registry.plugin import GraphNodeExecutorRegistry
from lca.nodes.loop.topology.plugin import TopologyGraphNodeExecutor


def build_default_graph_node_executor_registry() -> GraphNodeExecutorRegistry:
    """Create the same complete node primitive set declared by web-app.yaml."""

    registry = GraphNodeExecutorRegistry()
    registry.register(NodeType.AGENT, AgentGraphNodeExecutor())
    registry.register(NodeType.AGGREGATOR, AggregatorGraphNodeExecutor())
    for node_type in (NodeType.ENTRY, NodeType.EXIT, NodeType.ROUTER):
        registry.register(node_type, TopologyGraphNodeExecutor(node_type))
    return registry


__all__ = ["build_default_graph_node_executor_registry"]
