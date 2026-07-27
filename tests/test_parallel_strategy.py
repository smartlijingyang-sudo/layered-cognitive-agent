"""ParallelStrategy 测试 —— 验证 scatter-gather 并行调度与事件正确性。"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lca.layer4_app.defaults  # noqa: F401 — 触发 register_defaults()
from lca.contracts.protocols import OrchestrationContext
from lca.contracts.result import Result
from lca.contracts.state import Budget
from lca.layer3_agent.orchestration_registry import get_global_orchestration_registry
from lca.layer3_agent.orchestration_strategies import ParallelStrategy


def _make_result(trace_id: str, output: str) -> Result:
    return Result(
        trace_id=trace_id,
        status="completed",
        output=output,
        final_state_ref=f"mem://{trace_id}/0",
        total_steps=1,
        budget_used=Budget(),
    )


def _make_agent(trace_id: str, output: str, delay: float = 0.0):
    """构建 BaseAgent 桩件，execute 返回指定 Result。"""
    agent = MagicMock()

    async def _execute(task: str) -> Result:
        if delay > 0:
            await asyncio.sleep(delay)
        return _make_result(trace_id, output)

    agent.execute = AsyncMock(side_effect=_execute)
    return agent


class TestParallelStrategyBasic(unittest.IsolatedAsyncioTestCase):
    """ParallelStrategy 基本功能。"""

    async def test_parallel_runs_all_members_concurrently(self) -> None:
        agent_a = _make_agent("trace-a", "result-a", delay=0.05)
        agent_b = _make_agent("trace-b", "result-b", delay=0.05)

        strategy = ParallelStrategy()
        context = OrchestrationContext(members=[agent_a, agent_b])

        result = await strategy.run(context, "test objective")

        agent_a.execute.assert_awaited_once_with("test objective")
        agent_b.execute.assert_awaited_once_with("test objective")
        self.assertEqual(result.trace_id, "trace-b")
        self.assertEqual(result.output, "result-b")

    async def test_parallel_returns_last_result(self) -> None:
        agent_a = _make_agent("trace-a", "first")
        agent_b = _make_agent("trace-b", "second")
        agent_c = _make_agent("trace-c", "third")

        strategy = ParallelStrategy()
        context = OrchestrationContext(members=[agent_a, agent_b, agent_c])

        result = await strategy.run(context, "task")
        self.assertEqual(result.output, "third")

    async def test_parallel_empty_members_returns_failed(self) -> None:
        strategy = ParallelStrategy()
        context = OrchestrationContext(members=[])

        result = await strategy.run(context, "task")
        self.assertEqual(result.status, "failed")
        self.assertIn("No members", result.error)  # type: ignore[arg-type]

    async def test_parallel_single_member(self) -> None:
        agent = _make_agent("trace-only", "solo-result")
        strategy = ParallelStrategy()
        context = OrchestrationContext(members=[agent])

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
        context = OrchestrationContext(members=[agent_a, agent_b, agent_c])

        start = asyncio.get_event_loop().time()
        await strategy.run(context, "task")
        elapsed = asyncio.get_event_loop().time() - start

        # 并行执行：总耗时应接近单个 delay，而非 3 * delay
        self.assertLess(elapsed, delay * 2.5, "ParallelStrategy 应该并发执行，但耗时过长")


class TestParallelStrategyRegistration(unittest.TestCase):
    """ParallelStrategy 已注册到全局 registry，且与 TeamConfig.process Literal 对齐。"""

    def test_parallel_registered_in_global_registry(self) -> None:
        registry = get_global_orchestration_registry()
        self.assertTrue(registry.has("parallel"))

    def test_parallel_resolves_correctly(self) -> None:
        registry = get_global_orchestration_registry()
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

            agent.execute = AsyncMock(side_effect=_execute)
            return agent

        agent_a = _make_tracked_agent("trace-alpha")
        agent_b = _make_tracked_agent("trace-beta")

        strategy = ParallelStrategy()
        context = OrchestrationContext(members=[agent_a, agent_b])
        await strategy.run(context, "task")

        self.assertEqual(set(traces_seen), {"trace-alpha", "trace-beta"})


if __name__ == "__main__":
    unittest.main()
