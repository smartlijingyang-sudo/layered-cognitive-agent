"""编排策略覆盖测试 —— 确保 TeamConfig.process 的每个 Literal 值都有对应策略注册。

只要有人给 process 加新 Literal 值却忘了注册对应策略，这条测试当场失败。
"""

from __future__ import annotations

import os
import sys
import typing
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lca.layer4_app.defaults  # noqa: F401  — 触发 register_defaults() 填充全局注册表
from lca.contracts.role_team import TeamConfig
from lca.layer3_agent.orchestration_registry import get_global_orchestration_registry


def _get_process_literal_values() -> set[str]:
    """从 TeamConfig.process 的 Literal 类型中提取所有合法值。"""
    hints = typing.get_type_hints(TeamConfig)
    process_type = hints["process"]
    return set(typing.get_args(process_type))


class TestOrchestrationCoverage(unittest.IsolatedAsyncioTestCase):
    """TeamConfig.process 声明值集合 恒等于 OrchestrationStrategyRegistry 的 key 集合。"""

    def test_literal_values_match_registered_strategies(self) -> None:
        literal_values = _get_process_literal_values()
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

    async def test_graph_strategy_raises_not_implemented(self) -> None:
        """GraphStrategy 是占位实现，run() 应抛 NotImplementedError。"""
        from lca.contracts.protocols import OrchestrationContext
        from lca.layer3_agent.orchestration_strategies import GraphStrategy

        strategy = GraphStrategy()
        context = OrchestrationContext()
        with self.assertRaises(NotImplementedError):
            await strategy.run(context, "test")

    async def test_debate_strategy_raises_not_implemented(self) -> None:
        """DebateStrategy 是占位实现，run() 应抛 NotImplementedError。"""
        from lca.contracts.protocols import OrchestrationContext
        from lca.layer3_agent.orchestration_strategies import DebateStrategy

        strategy = DebateStrategy()
        context = OrchestrationContext()
        with self.assertRaises(NotImplementedError):
            await strategy.run(context, "test")


if __name__ == "__main__":
    unittest.main()
