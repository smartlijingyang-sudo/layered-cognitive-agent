"""Scenario 10 — self-improving (spec §13.6).

4-tier closed loop: skill acquisition + failure analysis + A/B testing +
capability extension.
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


class TestSelfImprovingScenario:
    """Spec §13.6: '自进化系统'."""

    def test_scenario_yaml_parses(self) -> None:
        scenario = load_scenario_yaml("self-improving")
        assert scenario["profile"]["id"] == "self-improving"

    def test_scenario_references_self_improving_bundle(self) -> None:
        scenario = load_scenario_yaml("self-improving")
        assert_scenario_references_bundles(scenario, "bundles/scenario-self-improving.yaml")

    def test_self_improving_bundle_loads(self) -> None:
        ids = assert_bundle_parses("scenario-self-improving")
        assert_min_plugin_count(ids, minimum=4, context="scenario-self-improving")

    def test_self_improving_plugins_are_closed_set(self) -> None:
        ids = assert_bundle_parses("scenario-self-improving")
        assert_plugins_are_closed(ids, context="scenario-self-improving")

    def test_self_improving_loop_config(self) -> None:
        scenario = load_scenario_yaml("self-improving")
        loop = scenario["profile"]["self_improving"]
        assert loop["skill_acquisition"]["enabled"] is True
        assert loop["profile_evolution"]["commit_threshold"] == 0.05

    @pytest.mark.asyncio
    async def test_self_improving_stub_run_returns_result(self) -> None:
        result = await run_stub_agent_async("hello world")
        assert result.status.value == "completed"
