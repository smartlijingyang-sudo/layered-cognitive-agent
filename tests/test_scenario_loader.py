"""Unit tests for tests/support/scenario_loader.py."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.support.scenario_loader import ScenarioSpec, build_team, load_scenario

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "team_scenarios"


class TestLoadScenario(unittest.TestCase):
    def test_load_ecommerce_launch_scenario(self) -> None:
        path = _FIXTURES_DIR / "ecommerce_launch.yaml"
        spec = load_scenario(path)

        self.assertIsInstance(spec, ScenarioSpec)
        self.assertIn("market_analyst", spec.roles)
        self.assertEqual(spec.roles["market_analyst"].role, "市场分析师")
        self.assertEqual(spec.roles["pricing_specialist"].tools, ["calculator"])
        self.assertIn("hierarchical", spec.teams)
        self.assertEqual(spec.teams["hierarchical"].lead_agent, "project_lead")
        self.assertEqual(spec.teams["hierarchical"].lead_mandate, "board")
        self.assertIsNone(spec.teams["hierarchical"].coordination)
        self.assertEqual(spec.teams["sequential"].coordination, "pipeline")
        self.assertIn("hierarchical_full_chain", spec.cases)

    def test_nonexistent_file_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            load_scenario("/nonexistent/path.yaml")

    def test_invalid_yaml_schema_raises(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("- just\n- a\n- list\n")
            f.flush()
            with self.assertRaises(ValueError):
                load_scenario(f.name)

    def test_team_kinds_present(self) -> None:
        spec = load_scenario(_FIXTURES_DIR / "ecommerce_launch.yaml")
        lead_teams = {k for k, t in spec.teams.items() if t.lead_agent is not None}
        coord_teams = {t.coordination for t in spec.teams.values() if t.coordination is not None}
        self.assertIn("hierarchical", lead_teams)
        self.assertEqual(coord_teams, {"pipeline", "fan_out", "peer_relay"})

    def test_all_cases_reference_valid_teams(self) -> None:
        spec = load_scenario(_FIXTURES_DIR / "ecommerce_launch.yaml")
        for case_key, case in spec.cases.items():
            self.assertIn(case.team, spec.teams, f"Case {case_key!r}")

    def test_all_team_members_reference_valid_roles(self) -> None:
        spec = load_scenario(_FIXTURES_DIR / "ecommerce_launch.yaml")
        for team_key, team in spec.teams.items():
            for member_key in team.members:
                self.assertIn(member_key, spec.roles, f"Team {team_key!r}")
            if team.lead_agent:
                self.assertIn(team.lead_agent, spec.roles, f"Team {team_key!r} lead")


class TestBuildTeam(unittest.TestCase):
    def test_build_sequential_team(self) -> None:
        from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter

        spec = load_scenario(_FIXTURES_DIR / "ecommerce_launch.yaml")
        team = build_team(spec, "sequential", MockLLMAdapter())
        self.assertIsNotNone(team)

    def test_build_hierarchical_team(self) -> None:
        from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter

        spec = load_scenario(_FIXTURES_DIR / "ecommerce_launch.yaml")
        team = build_team(spec, "hierarchical", MockLLMAdapter())
        self.assertIsNotNone(team)


if __name__ == "__main__":
    unittest.main()
