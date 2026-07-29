"""编排策略覆盖测试 —— 确保 TeamProcess 枚举的每个值都有对应策略注册。

只要有人给 TeamProcess 加新枚举值却忘了注册对应策略，这条测试当场失败。
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lca.contracts.enums import TeamProcess
from lca.layer3_agent.orchestration_registry import get_global_orchestration_registry
from lca.layer4_app.defaults import ensure_defaults

ensure_defaults()


def _get_process_enum_values() -> set[str]:
    """从 TeamProcess 枚举中提取所有合法值。"""
    return {m.value for m in TeamProcess}


class TestOrchestrationCoverage(unittest.IsolatedAsyncioTestCase):
    """TeamConfig.process 声明值集合 恒等于 OrchestrationStrategyRegistry 的 key 集合。"""

    def test_literal_values_match_registered_strategies(self) -> None:
        literal_values = _get_process_enum_values()
        registered = set(get_global_orchestration_registry().list_strategies())

        missing = literal_values - registered
        extra = registered - literal_values

        msg_parts: list[str] = []
        if missing:
            msg_parts.append(f"已声明但未注册策略: {missing}")
        if extra:
            msg_parts.append(f"已注册但未在 TeamConfig.process 中声明: {extra}")

        self.assertEqual(
            literal_values,
            registered,
            f"编排策略覆盖不完整: {'; '.join(msg_parts)}",
        )

    def test_resolve_unknown_strategy_raises_value_error(self) -> None:
        registry = get_global_orchestration_registry()
        with self.assertRaises(ValueError) as ctx:
            registry.resolve("nonexistent_strategy")
        self.assertIn("nonexistent_strategy", str(ctx.exception))

    async def test_graph_strategy_requires_execution_graph(self) -> None:
        """GraphStrategy 已落地实现，无 ExecutionGraph 时抛 ValueError。"""
        from lca.contracts.protocols import OrchestrationContext
        from lca.layer3_agent.orchestration_strategies import GraphStrategy

        strategy = GraphStrategy()
        context = OrchestrationContext()
        with self.assertRaises(ValueError):
            await strategy.run(context, "test")

    async def test_debate_strategy_is_functional(self) -> None:
        """DebateStrategy 已落地实现，run() 不再抛 NotImplementedError。"""
        from lca.contracts.protocols import OrchestrationContext
        from lca.contracts.result import Result
        from lca.contracts.state import Budget
        from lca.layer3_agent.orchestration_strategies import DebateStrategy

        strategy = DebateStrategy()
        agent = MagicMock()

        async def _execute(task: str) -> Result:
            return Result(
                trace_id="t1",
                status="completed",
                output="proposal",
                final_state_ref="",
                total_steps=1,
                budget_used=Budget(),
            )

        agent.execute = AsyncMock(side_effect=_execute)
        context = OrchestrationContext(members=[agent])
        result = await strategy.run(context, "test")
        self.assertEqual(result.status, "completed")


if __name__ == "__main__":
    unittest.main()
