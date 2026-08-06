"""编排策略覆盖测试 —— strategy key 集合与注册表一致。"""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock

from lca.contracts.models.team.team_coordination import (
    STRATEGY_KEY_DEBATE,
    STRATEGY_KEY_FAN_OUT,
    STRATEGY_KEY_GRAPH,
    STRATEGY_KEY_LEAD,
    STRATEGY_KEY_PEER_RELAY,
    STRATEGY_KEY_PEER_SWARM,
    STRATEGY_KEY_PIPELINE,
    Debate,
    Pipeline,
)
from lca.contracts.protocols import TeamAssembly
from lca.layer4_app.defaults import build_default_registries
from tests.support.team_stage import stage_with_invoker

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


def _assembly(governance=None) -> TeamAssembly:
    return TeamAssembly(
        governance=governance if governance is not None else Pipeline(),
        stage=stage_with_invoker([]),
    )


class TestOrchestrationCoverage(unittest.IsolatedAsyncioTestCase):
    def test_strategy_keys_match_registry(self) -> None:
        registered = set(_REGISTRIES.orchestration.list_strategies())
        self.assertEqual(_EXPECTED_KEYS, registered)

    def test_resolve_unknown_strategy_raises_value_error(self) -> None:
        registry = _REGISTRIES.orchestration
        with self.assertRaises(ValueError) as ctx:
            registry.resolve("nonexistent_strategy", _assembly())
        self.assertIn("nonexistent_strategy", str(ctx.exception))

    async def test_graph_strategy_requires_execution_graph(self) -> None:
        from lca.layer3_agent.orchestration_strategies import GraphStrategy

        with self.assertRaises(TypeError):
            GraphStrategy(stage_with_invoker([]))  # type: ignore[call-arg]

    async def test_debate_strategy_is_functional(self) -> None:
        from lca.contracts.models.core.result import Result
        from lca.contracts.models.core.state import Budget
        from lca.layer3_agent.orchestration_strategies import DebateStrategy

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
        strategy = DebateStrategy(stage_with_invoker([agent]), max_rounds=3)
        result = await strategy.run("test")
        self.assertEqual(result.status, "completed")

    def test_governance_keys_drive_registry_dispatch(self) -> None:
        """ADR-0034：strategy key 由 governance 单向派生，注册表按 key 分发。"""
        from lca.contracts.protocols.spec import strategy_key_for_governance

        self.assertEqual(strategy_key_for_governance(Pipeline()), STRATEGY_KEY_PIPELINE)
        self.assertEqual(strategy_key_for_governance(Debate()), STRATEGY_KEY_DEBATE)


if __name__ == "__main__":
    unittest.main()
