"""Scenario 7 — memgpt (spec §13.5.2).

4-layer memory (working/episodic/semantic/procedural) + MemGPT-style
CompactionPolicy paging.
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


class TestMemgptScenario:
    """Spec §13.5.2: 'MemGPT 风格分页 + 上下文压缩'."""

    def test_scenario_yaml_parses(self) -> None:
        scenario = load_scenario_yaml("memgpt")
        assert scenario["profile"]["id"] == "memgpt"

    def test_scenario_references_memgpt_bundle(self) -> None:
        scenario = load_scenario_yaml("memgpt")
        assert_scenario_references_bundles(scenario, "bundles/scenario-memgpt.yaml")

    def test_memgpt_bundle_loads(self) -> None:
        ids = assert_bundle_parses("scenario-memgpt")
        assert_min_plugin_count(ids, minimum=3, context="scenario-memgpt")

    def test_memgpt_plugins_are_closed_set(self) -> None:
        ids = assert_bundle_parses("scenario-memgpt")
        assert_plugins_are_closed(ids, context="scenario-memgpt")

    @pytest.mark.asyncio
    async def test_memgpt_stub_run_returns_result(self) -> None:
        result = await run_stub_agent_async("hello world")
        assert result.status.value == "completed"
