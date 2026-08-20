"""Scenario 3 — code (spec §13.2.1).

Standard + CodeMode executor strategy (SafeExecutor internal mode).
CodeMode is NOT a new primitive — it stays inside the SafeExecutor.
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


class TestCodeScenario:
    """Spec §13.2.1: '标准 + Code Mode SDK'."""

    def test_scenario_yaml_parses(self) -> None:
        scenario = load_scenario_yaml("code")
        assert scenario["profile"]["id"] == "code"

    def test_scenario_references_code_bundle(self) -> None:
        scenario = load_scenario_yaml("code")
        assert_scenario_references_bundles(scenario, "bundles/scenario-code.yaml")

    def test_code_bundle_loads(self) -> None:
        ids = assert_bundle_parses("scenario-code")
        assert_min_plugin_count(ids, minimum=3, context="scenario-code")

    def test_code_plugins_are_closed_set(self) -> None:
        ids = assert_bundle_parses("scenario-code")
        assert_plugins_are_closed(ids, context="scenario-code")

    @pytest.mark.asyncio
    async def test_code_stub_run_returns_result(self) -> None:
        result = await run_stub_agent_async("hello world")
        assert result.status.value == "completed"
