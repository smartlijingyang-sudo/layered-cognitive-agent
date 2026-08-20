"""Scenario 6 — voyager (spec §13.5.1).

Voyager-style skill acquisition.  Skill 习得 → procedural memory;
Critic 提炼。
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


class TestVoyagerScenario:
    """Spec §13.5.1: 'Voyager 风格技能习得 Agent'."""

    def test_scenario_yaml_parses(self) -> None:
        scenario = load_scenario_yaml("voyager")
        assert scenario["profile"]["id"] == "voyager"

    def test_scenario_references_voyager_bundle(self) -> None:
        scenario = load_scenario_yaml("voyager")
        assert_scenario_references_bundles(scenario, "bundles/scenario-voyager.yaml")

    def test_voyager_bundle_loads(self) -> None:
        ids = assert_bundle_parses("scenario-voyager")
        assert_min_plugin_count(ids, minimum=4, context="scenario-voyager")

    def test_voyager_plugins_are_closed_set(self) -> None:
        ids = assert_bundle_parses("scenario-voyager")
        assert_plugins_are_closed(ids, context="scenario-voyager")

    @pytest.mark.asyncio
    async def test_voyager_stub_run_returns_result(self) -> None:
        result = await run_stub_agent_async("hello world")
        assert result.status.value == "completed"
