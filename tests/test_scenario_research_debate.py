"""Scenario 12 — research-debate (spec §3.7.4).

Lead + 3 researchers (doc, code, web) + evidence synthesizer.  Uses
role-specific bundles (lead-standard, researcher-*-tools).
"""

from __future__ import annotations

import pytest

from tests.support.scenario_harness import (
    assert_bundle_parses,
    assert_min_plugin_count,
    assert_plugins_are_closed,
    load_scenario_yaml,
    run_stub_agent_async,
)


class TestResearchDebateScenario:
    """Spec §3.7.4: 'Lead + 3 researchers + evidence synthesizer'."""

    def test_scenario_yaml_parses(self) -> None:
        scenario = load_scenario_yaml("research-debate")
        assert scenario["team"]["members"][0]["role"] == "lead"

    def test_scenario_uses_debate_coordination(self) -> None:
        scenario = load_scenario_yaml("research-debate")
        assert scenario["team"]["governance"]["coordination"] == "Debate"

    def test_scenario_references_role_bundles(self) -> None:
        scenario = load_scenario_yaml("research-debate")
        members = scenario["team"]["members"]
        bundles = [m.get("bundle") for m in members if isinstance(m, dict)]
        # The lead + 3 researchers each declare a role bundle.
        assert "bundles/lead-standard.yaml" in bundles
        assert "bundles/researcher-doc-tools.yaml" in bundles
        assert "bundles/researcher-code-tools.yaml" in bundles
        assert "bundles/researcher-web-tools.yaml" in bundles

    def test_role_bundles_load(self) -> None:
        for name in (
            "lead-standard",
            "researcher-doc-tools",
            "researcher-code-tools",
            "researcher-web-tools",
        ):
            ids = assert_bundle_parses(name)
            assert_min_plugin_count(ids, minimum=2, context=name)

    def test_role_bundle_plugins_are_closed_set(self) -> None:
        for name in (
            "lead-standard",
            "researcher-doc-tools",
            "researcher-code-tools",
            "researcher-web-tools",
        ):
            ids = assert_bundle_parses(name)
            assert_plugins_are_closed(ids, context=name)

    @pytest.mark.asyncio
    async def test_research_debate_stub_run_returns_result(self) -> None:
        result = await run_stub_agent_async("hello world")
        assert result.status.value == "completed"
