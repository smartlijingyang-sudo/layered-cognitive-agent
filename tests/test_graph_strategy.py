"""GraphStrategy + ExecutionGraph 测试 —— 拓扑校验、线性执行、条件分支、并行扇出扇入。"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lca.contracts.models.core.result import Result
from lca.contracts.models.core.state import Budget
from lca.contracts.models.team.graph import (
    ExecutionGraph,
    GraphEdge,
    GraphNode,
    GraphValidationError,
)
from lca.contracts.models.team.role_team import RoleProfile, ToolPermissionManifest
from lca.contracts.protocols import TeamAssembly
from lca.layer3_agent.orchestration_strategies import GraphStrategy
from tests.support.team_stage import stage_with_invoker


def _make_role_profile(role: str) -> RoleProfile:
    return RoleProfile(
        role=role,
        goal=f"Goal for {role}",
        backstory=f"Backstory for {role}",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
    )


def _make_result(trace_id: str, output: str) -> Result:
    return Result(
        trace_id=trace_id,
        status="completed",
        final_state_ref=f"mem://{trace_id}/0",
        total_steps=1,
        budget_used=Budget(),
        output=output,
    )


def _make_agent(role: str, output: str) -> MagicMock:
    agent = MagicMock()
    agent.role_profile = _make_role_profile(role)

    async def _execute(task: str) -> Result:
        return _make_result(f"trace-{role}", output)

    agent.run = AsyncMock(side_effect=_execute)
    return agent


# ─── ExecutionGraph 数据结构测试 ───


class TestExecutionGraphValidation(unittest.TestCase):
    """ExecutionGraph 拓扑校验。"""

    def test_valid_linear_graph(self) -> None:
        g = ExecutionGraph()
        g.add_node(GraphNode(id="entry", type="entry"))
        g.add_node(GraphNode(id="a", type="agent"))
        g.add_node(GraphNode(id="exit", type="exit"))
        g.add_edge(GraphEdge(source="entry", target="a"))
        g.add_edge(GraphEdge(source="a", target="exit"))
        g.validate()  # 不应抛异常

    def test_missing_entry_raises(self) -> None:
        g = ExecutionGraph()
        g.add_node(GraphNode(id="a", type="agent"))
        g.add_node(GraphNode(id="exit", type="exit"))
        with self.assertRaises(GraphValidationError) as ctx:
            g.validate()
        self.assertIn("entry", str(ctx.exception))

    def test_missing_exit_raises(self) -> None:
        g = ExecutionGraph()
        g.add_node(GraphNode(id="entry", type="entry"))
        g.add_node(GraphNode(id="a", type="agent"))
        with self.assertRaises(GraphValidationError) as ctx:
            g.validate()
        self.assertIn("exit", str(ctx.exception))

    def test_invalid_edge_source(self) -> None:
        g = ExecutionGraph()
        g.add_node(GraphNode(id="entry", type="entry"))
        g.add_node(GraphNode(id="exit", type="exit"))
        g.add_edge(GraphEdge(source="nonexistent", target="exit"))
        with self.assertRaises(GraphValidationError):
            g.validate()

    def test_invalid_edge_target(self) -> None:
        g = ExecutionGraph()
        g.add_node(GraphNode(id="entry", type="entry"))
        g.add_node(GraphNode(id="exit", type="exit"))
        g.add_edge(GraphEdge(source="entry", target="nonexistent"))
        with self.assertRaises(GraphValidationError):
            g.validate()

    def test_cycle_detection(self) -> None:
        g = ExecutionGraph()
        g.add_node(GraphNode(id="entry", type="entry"))
        g.add_node(GraphNode(id="a", type="agent"))
        g.add_node(GraphNode(id="exit", type="exit"))
        g.add_edge(GraphEdge(source="entry", target="a"))
        g.add_edge(GraphEdge(source="a", target="exit"))
        g.add_edge(GraphEdge(source="exit", target="a"))  # 形成环
        with self.assertRaises(GraphValidationError) as ctx:
            g.validate()
        self.assertIn("环", str(ctx.exception))

    def test_allow_cycle_skips_cycle_check(self) -> None:
        g = ExecutionGraph(allow_cycle=True)
        g.add_node(GraphNode(id="entry", type="entry"))
        g.add_node(GraphNode(id="a", type="agent"))
        g.add_node(GraphNode(id="exit", type="exit"))
        g.add_edge(GraphEdge(source="entry", target="a"))
        g.add_edge(GraphEdge(source="a", target="exit"))
        g.add_edge(GraphEdge(source="exit", target="a"))
        g.validate()  # allow_cycle=True，不抛异常

    def test_topological_order(self) -> None:
        g = ExecutionGraph()
        g.add_node(GraphNode(id="entry", type="entry"))
        g.add_node(GraphNode(id="a", type="agent"))
        g.add_node(GraphNode(id="b", type="agent"))
        g.add_node(GraphNode(id="exit", type="exit"))
        g.add_edge(GraphEdge(source="entry", target="a"))
        g.add_edge(GraphEdge(source="a", target="b"))
        g.add_edge(GraphEdge(source="b", target="exit"))

        order = g.topological_order()
        self.assertEqual(order.index("entry"), 0)
        self.assertLess(order.index("a"), order.index("b"))
        self.assertLess(order.index("b"), order.index("exit"))

    def test_diamond_graph_valid(self) -> None:
        """菱形图（fan-out + fan-in）应通过校验。"""
        g = ExecutionGraph()
        g.add_node(GraphNode(id="entry", type="entry"))
        g.add_node(GraphNode(id="b", type="agent"))
        g.add_node(GraphNode(id="c", type="agent"))
        g.add_node(GraphNode(id="exit", type="exit"))
        g.add_edge(GraphEdge(source="entry", target="b", type="parallel"))
        g.add_edge(GraphEdge(source="entry", target="c", type="parallel"))
        g.add_edge(GraphEdge(source="b", target="exit"))
        g.add_edge(GraphEdge(source="c", target="exit"))
        g.validate()


# ─── GraphStrategy 执行测试 ───


class TestGraphStrategyLinearExecution(unittest.IsolatedAsyncioTestCase):
    """线性图执行（等价于 Sequential）。"""

    async def test_linear_graph_executes_in_order(self) -> None:
        """entry → A → exit 线性图应按序执行。"""
        execution_order: list[str] = []

        def _make_tracked_agent(role: str, output: str) -> MagicMock:
            agent = MagicMock()
            agent.role_profile = _make_role_profile(role)

            async def _execute(task: str) -> Result:
                execution_order.append(role)
                return _make_result(f"trace-{role}", output)

            agent.run = AsyncMock(side_effect=_execute)
            return agent

        agent_a = _make_tracked_agent("analyst", "analysis result")
        agent_w = _make_tracked_agent("writer", "final draft")

        graph = ExecutionGraph()
        graph.add_node(GraphNode(id="entry", type="entry"))
        graph.add_node(GraphNode(id="analyst", type="agent", config={"role": "analyst"}))
        graph.add_node(GraphNode(id="writer", type="agent", config={"role": "writer"}))
        graph.add_node(GraphNode(id="exit", type="exit"))
        graph.add_edge(GraphEdge(source="entry", target="analyst"))
        graph.add_edge(GraphEdge(source="analyst", target="writer"))
        graph.add_edge(GraphEdge(source="writer", target="exit"))

        strategy = GraphStrategy(stage_with_invoker([agent_a, agent_w]), execution_graph=graph)

        result = await strategy.run("write a report")

        self.assertEqual(execution_order, ["analyst", "writer"])
        self.assertEqual(result.output, "final draft")

    async def test_graph_required_at_construction(self) -> None:
        with self.assertRaises(TypeError):
            GraphStrategy(stage_with_invoker([]))  # type: ignore[call-arg]


class TestGraphStrategyConditionalEdge(unittest.IsolatedAsyncioTestCase):
    """条件分支。"""

    async def test_conditional_takes_matching_branch(self) -> None:
        """条件为 True 的边应被执行。"""
        agent_a = _make_agent("analyst", "analysis")
        agent_b = _make_agent("reviewer", "review")

        graph = ExecutionGraph()
        graph.add_node(GraphNode(id="entry", type="entry"))
        graph.add_node(GraphNode(id="analyst", type="agent", config={"role": "analyst"}))
        graph.add_node(GraphNode(id="reviewer", type="agent", config={"role": "reviewer"}))
        graph.add_node(GraphNode(id="exit", type="exit"))
        graph.add_edge(GraphEdge(source="entry", target="analyst"))
        graph.add_edge(
            GraphEdge(
                source="analyst",
                target="reviewer",
                type="conditional",
                condition=lambda state: True,
            )
        )
        graph.add_edge(GraphEdge(source="analyst", target="exit"))
        graph.add_edge(GraphEdge(source="reviewer", target="exit"))

        strategy = GraphStrategy(stage_with_invoker([agent_a, agent_b]), execution_graph=graph)

        result = await strategy.run("task")

        agent_a.run.assert_awaited_once()
        agent_b.run.assert_awaited_once()
        self.assertEqual(result.output, "review")

    async def test_conditional_skips_non_matching(self) -> None:
        """条件为 False 的边应被跳过。"""
        agent_a = _make_agent("analyst", "analysis")
        agent_s = _make_agent("skip_me", "should not run")

        graph = ExecutionGraph()
        graph.add_node(GraphNode(id="entry", type="entry"))
        graph.add_node(GraphNode(id="analyst", type="agent", config={"role": "analyst"}))
        graph.add_node(GraphNode(id="skip_me", type="agent", config={"role": "skip_me"}))
        graph.add_node(GraphNode(id="exit", type="exit"))
        graph.add_edge(GraphEdge(source="entry", target="analyst"))
        graph.add_edge(
            GraphEdge(
                source="analyst",
                target="skip_me",
                type="conditional",
                condition=lambda state: False,
            )
        )
        graph.add_edge(GraphEdge(source="analyst", target="exit"))
        graph.add_edge(GraphEdge(source="skip_me", target="exit"))

        strategy = GraphStrategy(stage_with_invoker([agent_a, agent_s]), execution_graph=graph)

        result = await strategy.run("task")

        agent_a.run.assert_awaited_once()
        agent_s.run.assert_not_awaited()
        self.assertEqual(result.output, "analysis")


class TestGraphStrategyParallelFanOut(unittest.IsolatedAsyncioTestCase):
    """并行扇出/扇入。"""

    async def test_parallel_fan_out_executes_all(self) -> None:
        """parallel 边应并发执行所有目标。"""
        agent_b = _make_agent("b", "result-b")
        agent_c = _make_agent("c", "result-c")

        graph = ExecutionGraph()
        graph.add_node(GraphNode(id="entry", type="entry"))
        graph.add_node(GraphNode(id="b", type="agent", config={"role": "b"}))
        graph.add_node(GraphNode(id="c", type="agent", config={"role": "c"}))
        graph.add_node(GraphNode(id="exit", type="exit"))
        graph.add_edge(GraphEdge(source="entry", target="b", type="parallel"))
        graph.add_edge(GraphEdge(source="entry", target="c", type="parallel"))
        graph.add_edge(GraphEdge(source="b", target="exit"))
        graph.add_edge(GraphEdge(source="c", target="exit"))

        strategy = GraphStrategy(stage_with_invoker([agent_b, agent_c]), execution_graph=graph)

        result = await strategy.run("task")

        agent_b.run.assert_awaited_once()
        agent_c.run.assert_awaited_once()
        self.assertIsNotNone(result)

    async def test_parallel_fan_out_is_concurrent(self) -> None:
        """parallel 边应真正并发执行（总耗时 < 各成员耗时之和）。"""
        import asyncio

        def _make_slow_agent(role: str, delay: float) -> MagicMock:
            agent = MagicMock()
            agent.role_profile = _make_role_profile(role)

            async def _execute(task: str) -> Result:
                await asyncio.sleep(delay)
                return _make_result(f"trace-{role}", f"result-{role}")

            agent.run = AsyncMock(side_effect=_execute)
            return agent

        agent_b = _make_slow_agent("b", 0.1)
        agent_c = _make_slow_agent("c", 0.1)

        graph = ExecutionGraph()
        graph.add_node(GraphNode(id="entry", type="entry"))
        graph.add_node(GraphNode(id="b", type="agent", config={"role": "b"}))
        graph.add_node(GraphNode(id="c", type="agent", config={"role": "c"}))
        graph.add_node(GraphNode(id="exit", type="exit"))
        graph.add_edge(GraphEdge(source="entry", target="b", type="parallel"))
        graph.add_edge(GraphEdge(source="entry", target="c", type="parallel"))
        graph.add_edge(GraphEdge(source="b", target="exit"))
        graph.add_edge(GraphEdge(source="c", target="exit"))

        strategy = GraphStrategy(stage_with_invoker([agent_b, agent_c]), execution_graph=graph)

        start = asyncio.get_event_loop().time()
        await strategy.run("task")
        elapsed = asyncio.get_event_loop().time() - start

        self.assertLess(elapsed, 0.25, "parallel 边应并发执行，但耗时过长")


class TestGraphStrategyRegistration(unittest.TestCase):
    """GraphStrategy 注册与解析（工厂接收 TeamAssembly，ADR-0034）。"""

    def test_graph_registered_by_default(self) -> None:
        from lca.contracts.models.team.team_coordination import STRATEGY_KEY_GRAPH
        from lca.layer4_app.defaults import build_default_registries

        registry = build_default_registries().orchestration
        self.assertTrue(registry.has(STRATEGY_KEY_GRAPH))

    def test_graph_resolves_correctly(self) -> None:
        from lca.contracts.models.team.team_coordination import STRATEGY_KEY_GRAPH, Graph
        from lca.layer4_app.defaults import build_default_registries

        registry = build_default_registries().orchestration
        assembly = TeamAssembly(
            governance=Graph(execution_graph=ExecutionGraph()), stage=stage_with_invoker([])
        )
        strategy = registry.resolve(STRATEGY_KEY_GRAPH, assembly)
        self.assertIsInstance(strategy, GraphStrategy)

    def test_graph_requires_graph_coordination(self) -> None:
        from lca.contracts.models.team.team_coordination import STRATEGY_KEY_GRAPH, Pipeline
        from lca.layer4_app.defaults import build_default_registries

        registry = build_default_registries().orchestration
        assembly = TeamAssembly(governance=Pipeline(), stage=stage_with_invoker([]))
        with self.assertRaises(TypeError):
            registry.resolve(STRATEGY_KEY_GRAPH, assembly)


if __name__ == "__main__":
    unittest.main()
