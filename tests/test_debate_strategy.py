"""DebateStrategy 测试 —— 多轮收敛、超时熔断、仲裁正确性。"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lca.contracts.protocols import OrchestrationContext
from lca.contracts.result import Result
from lca.contracts.role_team import TeamConfig
from lca.contracts.state import Budget
from lca.layer1_cognitive.brain.map_modules import (
    SimpleConflictMonitor,
    SimpleStateEvaluator,
    SimpleTaskCoordinator,
)
from lca.layer3_agent.orchestration_registry import get_global_orchestration_registry
from lca.layer3_agent.orchestration_strategies import DebateStrategy
from lca.layer4_app.defaults import ensure_defaults

ensure_defaults()


def _make_result(trace_id: str, output: str, status: str = "completed") -> Result:
    return Result(
        trace_id=trace_id,
        status=status,  # type: ignore[arg-type]
        final_state_ref=f"mem://{trace_id}/0",
        total_steps=1,
        budget_used=Budget(),
        output=output,
    )


def _make_agent(trace_id: str, outputs: list[str], status: str = "completed") -> MagicMock:
    """构建 Agent 桩件，按调用顺序返回不同 output。"""
    agent = MagicMock()
    call_count = 0

    async def _execute(task: str) -> Result:
        nonlocal call_count
        output = outputs[min(call_count, len(outputs) - 1)]
        call_count += 1
        return _make_result(trace_id, output, status=status)

    agent.execute = AsyncMock(side_effect=_execute)
    return agent


class TestDebateStrategyConvergence(unittest.IsolatedAsyncioTestCase):
    """验证多轮辩论收敛行为。"""

    async def test_single_member_converges_immediately(self) -> None:
        """单成员时，ConflictMonitor 返回空 → 第 1 轮即退出。"""
        agent = _make_agent("t1", ["only proposal"])
        strategy = DebateStrategy(
            conflict_monitor=SimpleConflictMonitor(),
            task_coordinator=SimpleTaskCoordinator(),
            state_evaluator=SimpleStateEvaluator(),
        )
        context = OrchestrationContext(members=[agent])

        result = await strategy.run(context, "task")

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.output, "only proposal")
        self.assertEqual(agent.execute.call_count, 1)

    async def test_early_exit_when_no_conflicts(self) -> None:
        """ConflictMonitor 第 1 轮返回空 → 提前退出，不跑满 max_rounds。"""
        agent_a = _make_agent("t-a", ["proposal-a"])
        agent_b = _make_agent("t-b", ["proposal-b"])

        monitor = MagicMock()
        monitor.check = AsyncMock(return_value=[])

        strategy = DebateStrategy(
            conflict_monitor=monitor,
            task_coordinator=SimpleTaskCoordinator(),
            state_evaluator=SimpleStateEvaluator(),
        )
        context = OrchestrationContext(
            members=[agent_a, agent_b],
            config=TeamConfig(process="debate", max_rounds=5),
        )

        result = await strategy.run(context, "task")

        self.assertEqual(result.status, "completed")
        self.assertEqual(agent_a.execute.call_count, 1)
        self.assertEqual(agent_b.execute.call_count, 1)

    async def test_convergence_after_rounds(self) -> None:
        """前 N-1 轮有分歧，第 N 轮收敛。"""
        agent_a = _make_agent("t-a", ["A1", "A2", "consensus"])
        agent_b = _make_agent("t-b", ["B1", "B2", "consensus"])

        monitor = MagicMock()
        monitor.check = AsyncMock(
            side_effect=[
                ["disagreement"],
                ["disagreement"],
                [],
            ]
        )

        strategy = DebateStrategy(
            conflict_monitor=monitor,
            task_coordinator=SimpleTaskCoordinator(),
            state_evaluator=SimpleStateEvaluator(),
        )
        context = OrchestrationContext(
            members=[agent_a, agent_b],
            config=TeamConfig(process="debate", max_rounds=5),
        )

        result = await strategy.run(context, "task")

        self.assertEqual(result.status, "completed")
        self.assertEqual(agent_a.execute.call_count, 3)
        self.assertEqual(agent_b.execute.call_count, 3)


class TestDebateStrategyMaxRounds(unittest.IsolatedAsyncioTestCase):
    """验证超时熔断（max_rounds 上限）。"""

    async def test_max_rounds_limit(self) -> None:
        """始终有分歧时，跑满 max_rounds 后返回最后一轮结果。"""
        agent_a = _make_agent("t-a", ["A1", "A2", "A3"])
        agent_b = _make_agent("t-b", ["B1", "B2", "B3"])

        monitor = MagicMock()
        monitor.check = AsyncMock(return_value=["disagreement"])

        strategy = DebateStrategy(
            conflict_monitor=monitor,
            task_coordinator=SimpleTaskCoordinator(),
            state_evaluator=SimpleStateEvaluator(),
        )
        context = OrchestrationContext(
            members=[agent_a, agent_b],
            config=TeamConfig(process="debate", max_rounds=2),
        )

        result = await strategy.run(context, "task")

        self.assertEqual(result.status, "completed")
        self.assertEqual(agent_a.execute.call_count, 2)
        self.assertEqual(agent_b.execute.call_count, 2)

    async def test_default_max_rounds_is_three(self) -> None:
        """未指定 max_rounds 时默认 3 轮。"""
        agent_a = _make_agent("t-a", ["A1", "A2", "A3"])
        agent_b = _make_agent("t-b", ["B1", "B2", "B3"])

        monitor = MagicMock()
        monitor.check = AsyncMock(return_value=["disagreement"])

        strategy = DebateStrategy(
            conflict_monitor=monitor,
            task_coordinator=SimpleTaskCoordinator(),
            state_evaluator=SimpleStateEvaluator(),
        )
        context = OrchestrationContext(members=[agent_a, agent_b])

        await strategy.run(context, "task")

        self.assertEqual(agent_a.execute.call_count, 3)

    async def test_objective_augmented_with_proposals(self) -> None:
        """每轮 objective 应包含前一轮各 Agent 的提案。"""
        seen_objectives: list[str] = []

        def _make_tracking_agent(trace_id: str, output: str) -> MagicMock:
            agent = MagicMock()

            async def _execute(task: str) -> Result:
                seen_objectives.append(task)
                return _make_result(trace_id, output)

            agent.execute = AsyncMock(side_effect=_execute)
            return agent

        agent_a = _make_tracking_agent("t-a", "proposal-a")
        agent_b = _make_tracking_agent("t-b", "proposal-b")

        monitor = MagicMock()
        monitor.check = AsyncMock(side_effect=[["conflict"], []])

        strategy = DebateStrategy(
            conflict_monitor=monitor,
            task_coordinator=SimpleTaskCoordinator(),
            state_evaluator=SimpleStateEvaluator(),
        )
        context = OrchestrationContext(
            members=[agent_a, agent_b],
            config=TeamConfig(process="debate", max_rounds=3),
        )

        await strategy.run(context, "original task")

        self.assertEqual(seen_objectives[0], "original task")
        self.assertIn("Previous proposals", seen_objectives[2])
        self.assertIn("proposal-a", seen_objectives[2])
        self.assertIn("proposal-b", seen_objectives[2])


class TestDebateStrategyArbitration(unittest.IsolatedAsyncioTestCase):
    """验证仲裁正确性。"""

    async def test_arbitration_selects_best_score(self) -> None:
        """TaskCoordinator 应选出 StateEvaluator 打分最高的候选。"""
        agent_a = _make_agent("t-a", ["weak"])
        agent_b = _make_agent("t-b", ["strong"])

        evaluator = MagicMock()
        evaluator.score = AsyncMock(side_effect=[0.3, 0.9])

        strategy = DebateStrategy(
            conflict_monitor=SimpleConflictMonitor(),
            task_coordinator=SimpleTaskCoordinator(),
            state_evaluator=evaluator,
        )
        context = OrchestrationContext(members=[agent_a, agent_b])

        result = await strategy.run(context, "task")

        self.assertEqual(result.output, "strong")

    async def test_arbitration_with_uniform_scores(self) -> None:
        """所有候选得分相同时，SimpleTaskCoordinator 选第一个（index 0）。"""
        agent_a = _make_agent("t-a", ["first"])
        agent_b = _make_agent("t-b", ["second"])

        strategy = DebateStrategy(
            conflict_monitor=SimpleConflictMonitor(),
            task_coordinator=SimpleTaskCoordinator(),
            state_evaluator=SimpleStateEvaluator(),
        )
        context = OrchestrationContext(members=[agent_a, agent_b])

        result = await strategy.run(context, "task")

        self.assertEqual(result.output, "first")


class TestDebateStrategyEdgeCases(unittest.IsolatedAsyncioTestCase):
    """边界情况。"""

    async def test_empty_members_returns_failed(self) -> None:
        strategy = DebateStrategy()
        context = OrchestrationContext(members=[])

        result = await strategy.run(context, "task")

        self.assertEqual(result.status, "failed")
        self.assertIn("No members", result.error)  # type: ignore[arg-type]

    async def test_no_components_still_works(self) -> None:
        """无 ConflictMonitor/Coordinator/Evaluator 时退化：跑满轮数返回首个结果。"""
        agent = _make_agent("t1", ["solo"])
        strategy = DebateStrategy()
        context = OrchestrationContext(
            members=[agent],
            config=TeamConfig(process="debate", max_rounds=1),
        )

        result = await strategy.run(context, "task")

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.output, "solo")

    async def test_failed_member_output(self) -> None:
        """成员返回 failed 状态时，debate 仍能继续。"""
        agent_a = _make_agent("t-a", ["good"], status="completed")
        agent_b = _make_agent("t-b", [""], status="failed")

        strategy = DebateStrategy(
            conflict_monitor=SimpleConflictMonitor(),
            task_coordinator=SimpleTaskCoordinator(),
            state_evaluator=SimpleStateEvaluator(),
        )
        context = OrchestrationContext(
            members=[agent_a, agent_b],
            config=TeamConfig(process="debate", max_rounds=1),
        )

        result = await strategy.run(context, "task")

        self.assertEqual(result.status, "completed")


class TestDebateStrategyRegistration(unittest.TestCase):
    """DebateStrategy 注册与解析。"""

    def test_debate_registered_in_global_registry(self) -> None:
        registry = get_global_orchestration_registry()
        self.assertTrue(registry.has("debate"))

    def test_debate_resolves_with_components(self) -> None:
        registry = get_global_orchestration_registry()
        strategy = registry.resolve("debate")
        self.assertIsInstance(strategy, DebateStrategy)
        self.assertIsNotNone(strategy._conflict_monitor)
        self.assertIsNotNone(strategy._task_coordinator)
        self.assertIsNotNone(strategy._state_evaluator)


if __name__ == "__main__":
    unittest.main()
