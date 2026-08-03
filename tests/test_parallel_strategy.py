"""ParallelStrategy 测试 —— 验证 scatter-gather 并行调度与事件正确性。"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lca.contracts.lifecycle import TaskStatus
from lca.contracts.protocols import TeamContext
from lca.contracts.result import Result
from lca.contracts.state import Budget
from lca.layer3_agent.orchestration_strategies import (
    ParallelStrategy,
)
from lca.layer4_app.defaults import build_default_registries
from tests.support.team_context import team_context_with_transport

_REGISTRIES = build_default_registries()


def _make_result(trace_id: str, output: str) -> Result:
    return Result(
        trace_id=trace_id,
        status=TaskStatus.COMPLETED,
        output=output,
        final_state_ref=f"mem://{trace_id}/0",
        total_steps=1,
        budget_used=Budget(),
    )


def _make_agent(trace_id: str, output: str, delay: float = 0.0):
    """构建 CognitiveAgent 桩件，run 返回指定 Result。"""
    agent = MagicMock()
    agent.role_profile = MagicMock()
    agent.role_profile.role = trace_id

    async def _execute(task: str) -> Result:
        if delay > 0:
            await asyncio.sleep(delay)
        return _make_result(trace_id, output)

    agent.run = AsyncMock(side_effect=_execute)
    return agent


class TestParallelStrategyBasic(unittest.IsolatedAsyncioTestCase):
    """ParallelStrategy 基本功能。"""

    async def test_parallel_runs_all_members_concurrently(self) -> None:
        agent_a = _make_agent("trace-a", "result-a", delay=0.05)
        agent_b = _make_agent("trace-b", "result-b", delay=0.05)

        strategy = ParallelStrategy()
        context = team_context_with_transport([agent_a, agent_b])

        result = await strategy.run(context, "test objective")

        agent_a.run.assert_awaited_once_with("test objective")
        agent_b.run.assert_awaited_once_with("test objective")
        self.assertEqual(result.trace_id, "trace-b")
        self.assertEqual(result.output, "result-b")

    async def test_parallel_returns_last_result(self) -> None:
        agent_a = _make_agent("trace-a", "first")
        agent_b = _make_agent("trace-b", "second")
        agent_c = _make_agent("trace-c", "third")

        strategy = ParallelStrategy()
        context = team_context_with_transport([agent_a, agent_b, agent_c])

        result = await strategy.run(context, "task")
        self.assertEqual(result.output, "third")

    async def test_parallel_empty_members_returns_failed(self) -> None:
        strategy = ParallelStrategy()
        context = TeamContext(members=[])

        result = await strategy.run(context, "task")
        self.assertEqual(result.status, "failed")
        self.assertIn("No members", result.error or "")

    async def test_parallel_single_member(self) -> None:
        agent = _make_agent("trace-only", "solo-result")
        strategy = ParallelStrategy()
        context = team_context_with_transport([agent])

        result = await strategy.run(context, "solo task")
        self.assertEqual(result.output, "solo-result")


class TestParallelStrategyConcurrency(unittest.IsolatedAsyncioTestCase):
    """验证并行策略确实并发执行（总耗时 < 各成员耗时之和）。"""

    async def test_parallel_is_faster_than_sequential(self) -> None:
        delay = 0.1
        agent_a = _make_agent("trace-a", "a", delay=delay)
        agent_b = _make_agent("trace-b", "b", delay=delay)
        agent_c = _make_agent("trace-c", "c", delay=delay)

        strategy = ParallelStrategy()
        context = team_context_with_transport([agent_a, agent_b, agent_c])

        start = asyncio.get_event_loop().time()
        await strategy.run(context, "task")
        elapsed = asyncio.get_event_loop().time() - start

        # 并行执行：总耗时应接近单个 delay，而非 3 * delay
        self.assertLess(elapsed, delay * 2.5, "ParallelStrategy 应该并发执行，但耗时过长")


class TestParallelStrategyRegistration(unittest.TestCase):
    """ParallelStrategy 默认已注册，且与 TeamConfig.process Literal 对齐。"""

    def test_parallel_registered_by_default(self) -> None:
        registry = _REGISTRIES.orchestration
        self.assertTrue(registry.has("parallel"))

    def test_parallel_resolves_correctly(self) -> None:
        registry = _REGISTRIES.orchestration
        strategy = registry.resolve("parallel")
        self.assertIsInstance(strategy, ParallelStrategy)


class TestParallelStrategyTraceIsolation(unittest.IsolatedAsyncioTestCase):
    """并行执行时，每个成员产生独立的 trace_id，互不干扰。"""

    async def test_each_member_has_independent_trace(self) -> None:
        traces_seen: list[str] = []

        def _make_tracked_agent(trace_id: str):
            agent = MagicMock()

            async def _execute(task: str) -> Result:
                traces_seen.append(trace_id)
                return _make_result(trace_id, f"output-{trace_id}")

            agent.run = AsyncMock(side_effect=_execute)
            return agent

        agent_a = _make_tracked_agent("trace-alpha")
        agent_b = _make_tracked_agent("trace-beta")

        strategy = ParallelStrategy()
        context = team_context_with_transport([agent_a, agent_b])
        await strategy.run(context, "task")

        self.assertEqual(set(traces_seen), {"trace-alpha", "trace-beta"})


if __name__ == "__main__":
    unittest.main()
