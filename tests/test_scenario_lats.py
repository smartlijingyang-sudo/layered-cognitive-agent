"""Scenario 9 — lats (spec §13.5.4).

Brain replacement + Critic + GoalStack tree search (MCTS-style).
"""

from __future__ import annotations

import pytest

from tests.support.scenario_harness import (
    assert_bundle_parses,
    assert_min_plugin_count,
    assert_plugins_are_closed,
    assert_scenario_references_bundles,
    load_scenario_yaml,
    run_stub_agent_async,
)


class TestLatsScenario:
    """Spec §13.5.4: 'LATS / MCTS 风格树搜索 + 价值评估'."""

    def test_scenario_yaml_parses(self) -> None:
        scenario = load_scenario_yaml("lats")
        assert scenario["profile"]["id"] == "lats"

    def test_scenario_references_lats_bundle(self) -> None:
        scenario = load_scenario_yaml("lats")
        assert_scenario_references_bundles(scenario, "bundles/scenario-lats.yaml")

    def test_lats_bundle_loads(self) -> None:
        ids = assert_bundle_parses("scenario-lats")
        assert_min_plugin_count(ids, minimum=3, context="scenario-lats")

    def test_lats_plugins_are_closed_set(self) -> None:
        ids = assert_bundle_parses("scenario-lats")
        assert_plugins_are_closed(ids, context="scenario-lats")

    def test_lats_brain_config_present(self) -> None:
        scenario = load_scenario_yaml("lats")
        brain = scenario["profile"]["brain"]
        assert brain["type"] == "lats"
        assert brain["n_simulations"] == 50

    @pytest.mark.asyncio
    async def test_lats_stub_run_returns_result(self) -> None:
        result = await run_stub_agent_async("hello world")
        assert result.status.value == "completed"
