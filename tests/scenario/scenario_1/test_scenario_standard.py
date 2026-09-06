"""Scenario 2 — standard (spec §13.2.1).

Full standard implementation: all primitives enabled, default Brain,
all Sensors, four-layer Memory.
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


class TestStandardScenario:
    """Spec §13.2.1: '功能完整的编码 Agent（标准实现）'."""

    def test_scenario_yaml_parses(self) -> None:
        scenario = load_scenario_yaml("standard")
        assert scenario["profile"]["id"] == "standard"

    def test_scenario_references_standard_bundle(self) -> None:
        scenario = load_scenario_yaml("standard")
        assert_scenario_references_bundles(scenario, "bundles/scenario-standard.yaml")

    def test_standard_bundle_loads(self) -> None:
        ids = assert_bundle_parses("scenario-standard")
        assert_min_plugin_count(ids, minimum=5, context="scenario-standard")

    def test_standard_plugins_are_closed_set(self) -> None:
        ids = assert_bundle_parses("scenario-standard")
        assert_plugins_are_closed(ids, context="scenario-standard")

    @pytest.mark.asyncio
    async def test_standard_stub_run_returns_result(self) -> None:
        result = await run_stub_agent_async("hello world")
        assert result.status.value == "completed"
