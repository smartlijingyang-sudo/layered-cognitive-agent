"""Scenario 8 — metagpt (spec §13.5.3).

Team XOR + Graph coordination + roles.  PM / Architect / Engineer / QA
multi-role PR-style document flow.
"""

from __future__ import annotations

import pytest

from tests.support.scenario_harness import (
    load_scenario_yaml,
    run_stub_agent_async,
)


class TestMetagptScenario:
    """Spec §13.5.3: 'metagpt 风格多角色 PR 文档流'."""

    def test_scenario_yaml_parses(self) -> None:
        scenario = load_scenario_yaml("metagpt")
        assert scenario["team"]["members"][0]["role"] == "pm"

    def test_scenario_uses_graph_coordination(self) -> None:
        scenario = load_scenario_yaml("metagpt")
        assert scenario["team"]["governance"]["coordination"] == "Graph"

    def test_scenario_team_xor_holds(self) -> None:
        scenario = load_scenario_yaml("metagpt")
        gov = scenario["team"]["governance"]
        # Graph coordination; no explicit lead in governance.
        assert "lead" not in gov
        assert "coordination" in gov

    def test_scenario_workflow_edges_present(self) -> None:
        scenario = load_scenario_yaml("metagpt")
        edges = scenario["team"]["governance"]["workflow_edges"]
        assert any(e["from"] == "pm" and e["to"] == "architect" for e in edges)

    @pytest.mark.asyncio
    async def test_metagpt_stub_run_returns_result(self) -> None:
        result = await run_stub_agent_async("hello world")
        assert result.status.value == "completed"
