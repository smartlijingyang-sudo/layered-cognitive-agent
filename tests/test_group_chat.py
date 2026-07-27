"""GroupChat 预置模板测试 —— mesh 拓扑构建、GraphStrategy 集成。"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lca.contracts.protocols import OrchestrationContext
from lca.contracts.result import Result
from lca.contracts.state import Budget
from lca.layer3_agent.group_chat import build_group_chat_graph
from lca.layer3_agent.orchestration_strategies import GraphStrategy


def _make_agent(role: str, output: str) -> MagicMock:
    agent = MagicMock()
    agent.role_profile = MagicMock()
    agent.role_profile.role = role

    async def _execute(task: str) -> Result:
        return Result(
            trace_id=f"trace-{role}",
            status="completed",
            final_state_ref="",
            total_steps=1,
            budget_used=Budget(),
            output=output,
        )

    agent.execute = AsyncMock(side_effect=_execute)
    return agent


class TestGroupChatGraphConstruction(unittest.TestCase):
    """群聊图拓扑构建。"""

    def test_full_mesh_has_all_edges(self) -> None:
        """全连接 mesh：每个 agent 到其他所有 agent 都有边。"""
        graph = build_group_chat_graph(["a", "b", "c"])
        roles = ["a", "b", "c"]

        for src in roles:
            for tgt in roles:
                if src != tgt:
                    edges = [e for e in graph.edges if e.source == src and e.target == tgt]
                    self.assertTrue(edges, f"缺少边 {src} → {tgt}")

    def test_each_agent_can_exit(self) -> None:
        """每个 agent 都有到 exit 的边。"""
        graph = build_group_chat_graph(["a", "b", "c"])
        for role in ["a", "b", "c"]:
            edges = [e for e in graph.edges if e.source == role and e.target == "exit"]
            self.assertTrue(edges, f"agent {role} 缺少到 exit 的边")

    def test_entry_connects_to_first(self) -> None:
        """entry 连接到第一个 agent。"""
        graph = build_group_chat_graph(["a", "b"])
        edges = [e for e in graph.edges if e.source == "entry"]
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0].target, "a")

    def test_sequential_mode(self) -> None:
        """非全连接模式：顺序传递。"""
        graph = build_group_chat_graph(["a", "b", "c"], allow_all_messages=False)

        # a → b, b → c, c → exit
        self.assertTrue(any(e.source == "a" and e.target == "b" for e in graph.edges))
        self.assertTrue(any(e.source == "b" and e.target == "c" for e in graph.edges))
        self.assertTrue(any(e.source == "c" and e.target == "exit" for e in graph.edges))

        # 不应有 a → c 的边
        self.assertFalse(any(e.source == "a" and e.target == "c" for e in graph.edges))

    def test_graph_validates(self) -> None:
        """构建的图应通过拓扑校验。"""
        graph = build_group_chat_graph(["a", "b", "c"])
        graph.validate()  # 不应抛异常

    def test_empty_roles(self) -> None:
        """空角色列表应构建只有 entry/exit 的图。"""
        graph = build_group_chat_graph([])
        self.assertEqual(len(graph.nodes), 2)  # entry + exit
        self.assertEqual(len(graph.edges), 0)


class TestGroupChatWithGraphStrategy(unittest.IsolatedAsyncioTestCase):
    """GroupChat 模板 + GraphStrategy 集成。"""

    async def test_sequential_chat_executes_in_order(self) -> None:
        """顺序模式下 agent 按序执行。"""
        execution_order: list[str] = []

        def _make_tracked(role: str, output: str) -> MagicMock:
            agent = MagicMock()
            agent.role_profile = MagicMock()
            agent.role_profile.role = role

            async def _execute(task: str) -> Result:
                execution_order.append(role)
                return Result(
                    trace_id=f"trace-{role}",
                    status="completed",
                    final_state_ref="",
                    total_steps=1,
                    budget_used=Budget(),
                    output=output,
                )

            agent.execute = AsyncMock(side_effect=_execute)
            return agent

        agents = [
            _make_tracked("alice", "alice says hi"),
            _make_tracked("bob", "bob replies"),
        ]

        graph = build_group_chat_graph(["alice", "bob"], allow_all_messages=False)
        strategy = GraphStrategy(execution_graph=graph)
        context = OrchestrationContext(members=agents)

        result = await strategy.run(context, "start chat")

        self.assertEqual(execution_order, ["alice", "bob"])
        self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()
