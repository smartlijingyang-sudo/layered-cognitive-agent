"""Scenario 11 — devin-style (spec §13.5.6).

GoalStack + Ralph + Team + ApprovalToken.  Connects GitHub Issue →
plan → implement → test → PR.
"""

from __future__ import annotations

import pytest

from tests.support.scenario_harness import (
    load_scenario_yaml,
    run_stub_agent_async,
)


class TestDevinStyleScenario:
    """Spec §13.5.6: 'Devin 风格 GitHub Issue → PR'."""

    def test_scenario_yaml_parses(self) -> None:
        scenario = load_scenario_yaml("devin-style")
        assert scenario["team"]["members"][0]["role"] == "planner"

    def test_scenario_uses_graph_coordination(self) -> None:
        scenario = load_scenario_yaml("devin-style")
        assert scenario["team"]["governance"]["coordination"] == "Graph"

    def test_scenario_workflow_edges_present(self) -> None:
        scenario = load_scenario_yaml("devin-style")
        edges = scenario["team"]["governance"]["workflow_edges"]
        assert any(e["from"] == "planner" and e["to"] == "implementer" for e in edges)

    def test_scenario_team_xor_holds(self) -> None:
        scenario = load_scenario_yaml("devin-style")
        gov = scenario["team"]["governance"]
        assert "lead" not in gov
        assert "coordination" in gov

    @pytest.mark.asyncio
    async def test_devin_style_stub_run_returns_result(self) -> None:
        result = await run_stub_agent_async("hello world")
        assert result.status.value == "completed"
