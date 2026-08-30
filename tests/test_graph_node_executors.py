"""Substitution tests for collaboration graph-node primitives."""

from __future__ import annotations

import unittest

from lca.contracts.models.core.result import Result
from lca.contracts.models.core.state import Budget
from lca.contracts.models.team.graph import ExecutionGraph, GraphEdge, GraphNode, NodeType
from lca.contracts.protocols import GraphNodeExecutionContext, GraphNodeExecutor
from lca.agent.orchestration_strategies import GraphStrategy
from lca.plugins.phase_graph.aggregator import AggregatorGraphNodeExecutor
from lca.plugins.phase_graph.registry import GraphNodeExecutorRegistry
from lca.plugins.phase_graph.topology import TopologyGraphNodeExecutor
from tests.support.team_stage import stage_with_invoker


class _RecordingAgentNode(GraphNodeExecutor):
    node_type = NodeType.AGENT
    is_aggregator = False

    def __init__(self) -> None:
        self.calls: list[GraphNodeExecutionContext] = []

    async def execute(self, context: GraphNodeExecutionContext) -> Result:
        self.calls.append(context)
        return Result(
            trace_id="custom-agent-node",
            status="completed",
            final_state_ref="",
            total_steps=1,
            budget_used=Budget(),
            output="custom node result",
        )


def _linear_graph() -> ExecutionGraph:
    graph = ExecutionGraph()
    graph.add_node(GraphNode(id="entry", type=NodeType.ENTRY))
    graph.add_node(GraphNode(id="custom", type=NodeType.AGENT, config={"role": "ignored"}))
    graph.add_node(GraphNode(id="exit", type=NodeType.EXIT))
    graph.add_edge(GraphEdge(source="entry", target="custom"))
    graph.add_edge(GraphEdge(source="custom", target="exit"))
    return graph


def _registry_with(agent_executor: GraphNodeExecutor | None) -> GraphNodeExecutorRegistry:
    registry = GraphNodeExecutorRegistry()
    for node_type in (NodeType.ENTRY, NodeType.EXIT, NodeType.ROUTER):
        registry.register(node_type, TopologyGraphNodeExecutor(node_type))
    registry.register(NodeType.AGGREGATOR, AggregatorGraphNodeExecutor())
    if agent_executor is not None:
        registry.register(NodeType.AGENT, agent_executor)
    return registry


class TestGraphNodeExecutorSubstitution(unittest.IsolatedAsyncioTestCase):
    async def test_custom_agent_node_runs_without_graph_strategy_changes(self) -> None:
        """A profile-selected node primitive owns the node behavior end to end."""

        custom_agent_node = _RecordingAgentNode()
        strategy = GraphStrategy(
            stage_with_invoker([]),
            execution_graph=_linear_graph(),
            node_executors=_registry_with(custom_agent_node),
        )

        result = await strategy.run("execute custom graph node")

        self.assertEqual(result.output, "custom node result")
        self.assertEqual(len(custom_agent_node.calls), 1)
        self.assertEqual(custom_agent_node.calls[0].node.id, "custom")
        self.assertEqual(custom_agent_node.calls[0].objective, "execute custom graph node")

    async def test_missing_node_primitive_fails_closed(self) -> None:
        """Graph traversal cannot silently fall back when a declared node has no provider."""

        strategy = GraphStrategy(
            stage_with_invoker([]),
            execution_graph=_linear_graph(),
            node_executors=_registry_with(None),
        )

        with self.assertRaisesRegex(KeyError, "no executor registered for 'agent'"):
            await strategy.run("missing node primitive")


class TestGraphNodeExecutorRegistry(unittest.TestCase):
    def test_registry_rejects_mismatched_executor_ownership(self) -> None:
        registry = GraphNodeExecutorRegistry()

        with self.assertRaisesRegex(ValueError, "must match"):
            registry.register(NodeType.AGENT, AggregatorGraphNodeExecutor())

    def test_registry_rejects_duplicate_node_ownership(self) -> None:
        registry = GraphNodeExecutorRegistry()
        registry.register(NodeType.AGGREGATOR, AggregatorGraphNodeExecutor())

        with self.assertRaisesRegex(KeyError, "already registered"):
            registry.register(NodeType.AGGREGATOR, AggregatorGraphNodeExecutor())
