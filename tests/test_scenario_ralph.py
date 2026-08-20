"""Scenario 5 — ralph-loop (spec §13.4).

Workflow automation patch-then-test cycle.  Fully assembled from v3
primitives; zero new primitives added.
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


class TestRalphLoopScenario:
    """Spec §13.4: 'Ralph loop 完全由 v3 现有原语组合实现，零新增原语'."""

    def test_scenario_yaml_parses(self) -> None:
        scenario = load_scenario_yaml("ralph-loop")
        assert scenario["profile"]["id"] == "ralph-loop"

    def test_scenario_references_ralph_bundle(self) -> None:
        scenario = load_scenario_yaml("ralph-loop")
        assert_scenario_references_bundles(scenario, "bundles/scenario-ralph.yaml")

    def test_ralph_bundle_loads(self) -> None:
        ids = assert_bundle_parses("scenario-ralph")
        assert_min_plugin_count(ids, minimum=5, context="scenario-ralph")

    def test_ralph_plugins_are_closed_set(self) -> None:
        ids = assert_bundle_parses("scenario-ralph")
        assert_plugins_are_closed(ids, context="scenario-ralph")

    @pytest.mark.asyncio
    async def test_ralph_stub_run_returns_result(self) -> None:
        result = await run_stub_agent_async("hello world")
        assert result.status.value == "completed"
