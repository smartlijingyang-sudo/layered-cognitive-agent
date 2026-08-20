"""Scenario 4 — cordis-creator (spec §13.3).

Standard + Composer.mount/unmount + cordis_control tool.  Creator uses
an ordinary Tool call (Body.act) to mount/unmount plugins.
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


class TestCordisCreatorScenario:
    """Spec §13.3: '标准 + 运行时检查 + 插件实验 + preset 创作'."""

    def test_scenario_yaml_parses(self) -> None:
        scenario = load_scenario_yaml("cordis-creator")
        assert scenario["profile"]["id"] == "cordis-creator"

    def test_scenario_references_cordis_creator_bundle(self) -> None:
        scenario = load_scenario_yaml("cordis-creator")
        assert_scenario_references_bundles(
            scenario, "bundles/scenario-cordis-creator.yaml"
        )

    def test_cordis_creator_bundle_loads(self) -> None:
        ids = assert_bundle_parses("scenario-cordis-creator")
        assert_min_plugin_count(ids, minimum=2, context="scenario-cordis-creator")

    def test_cordis_creator_plugins_are_closed_set(self) -> None:
        ids = assert_bundle_parses("scenario-cordis-creator")
        assert_plugins_are_closed(ids, context="scenario-cordis-creator")

    @pytest.mark.asyncio
    async def test_cordis_creator_stub_run_returns_result(self) -> None:
        result = await run_stub_agent_async("hello world")
        assert result.status.value == "completed"
