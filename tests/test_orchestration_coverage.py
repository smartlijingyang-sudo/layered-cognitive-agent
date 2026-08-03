"""编排策略覆盖测试 —— strategy key 集合与注册表一致。"""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock

from lca.contracts.team_coordination import (
    STRATEGY_KEY_DEBATE,
    STRATEGY_KEY_FAN_OUT,
    STRATEGY_KEY_GRAPH,
    STRATEGY_KEY_LEAD,
    STRATEGY_KEY_PEER_RELAY,
    STRATEGY_KEY_PEER_SWARM,
    STRATEGY_KEY_PIPELINE,
)
from lca.layer4_app.defaults import build_default_registries
from tests.support.team_context import team_context_with_transport

_REGISTRIES = build_default_registries()

_EXPECTED_KEYS = {
    STRATEGY_KEY_LEAD,
    STRATEGY_KEY_PIPELINE,
    STRATEGY_KEY_FAN_OUT,
    STRATEGY_KEY_DEBATE,
    STRATEGY_KEY_PEER_RELAY,
    STRATEGY_KEY_PEER_SWARM,
    STRATEGY_KEY_GRAPH,
}


class TestOrchestrationCoverage(unittest.IsolatedAsyncioTestCase):
    def test_strategy_keys_match_registry(self) -> None:
        registered = set(_REGISTRIES.orchestration.list_strategies())
        self.assertEqual(_EXPECTED_KEYS, registered)

    def test_resolve_unknown_strategy_raises_value_error(self) -> None:
        registry = _REGISTRIES.orchestration
        with self.assertRaises(ValueError) as ctx:
            registry.resolve("nonexistent_strategy")
        self.assertIn("nonexistent_strategy", str(ctx.exception))

    async def test_graph_strategy_requires_execution_graph(self) -> None:
        from lca.contracts.protocols import TeamContext
        from lca.layer3_agent.orchestration_strategies import GraphStrategy

        strategy = GraphStrategy()
        context = TeamContext()
        with self.assertRaises(ValueError):
            await strategy.run(context, "test")

    async def test_debate_strategy_is_functional(self) -> None:
        from lca.contracts.result import Result
        from lca.contracts.state import Budget
        from lca.layer3_agent.orchestration_strategies import DebateStrategy

        strategy = DebateStrategy()
        agent = MagicMock()
        agent.role_profile = MagicMock()
        agent.role_profile.role = "debater"

        async def _execute(task: str) -> Result:
            return Result(
                trace_id="t1",
                status="completed",
                output="proposal",
                final_state_ref="",
                total_steps=1,
                budget_used=Budget(),
            )

        agent.run = AsyncMock(side_effect=_execute)
        context = team_context_with_transport([agent])
        result = await strategy.run(context, "test")
        self.assertEqual(result.status, "completed")


if __name__ == "__main__":
    unittest.main()
