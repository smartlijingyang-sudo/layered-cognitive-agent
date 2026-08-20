"""Scenario 1 — minimal (spec §13.2.1).

Only bash + str_replace_editor tools; no memory, no skills, no decision
gates.  Per-agent primitives are Null by default.
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


class TestMinimalScenario:
    """Spec §13.2.1: 'bash + str_replace_editor 双工具编码 Agent（极简）'."""

    def test_scenario_yaml_parses(self) -> None:
        scenario = load_scenario_yaml("minimal")
        assert scenario["profile"]["id"] == "minimal"

    def test_scenario_references_minimal_bundle(self) -> None:
        scenario = load_scenario_yaml("minimal")
        assert_scenario_references_bundles(scenario, "bundles/scenario-minimal.yaml")

    def test_minimal_bundle_loads(self) -> None:
        ids = assert_bundle_parses("scenario-minimal")
        # 2 tools + 1 loop = 3 plugins minimum.
        assert_min_plugin_count(ids, minimum=3, context="scenario-minimal")

    def test_minimal_plugins_are_closed_set(self) -> None:
        ids = assert_bundle_parses("scenario-minimal")
        assert_plugins_are_closed(ids, context="scenario-minimal")

    @pytest.mark.asyncio
    async def test_minimal_stub_run_returns_result(self) -> None:
        result = await run_stub_agent_async("hello world")
        assert result.status.value == "completed"
        assert result.output == "hello world"
