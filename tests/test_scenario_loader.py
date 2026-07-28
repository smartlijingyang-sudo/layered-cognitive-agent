"""Unit tests for tests/support/scenario_loader.py."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.support.scenario_loader import (
    ScenarioSpec,
    load_scenario,
)

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "team_scenarios"


class TestLoadScenario(unittest.TestCase):
    """Tests for load_scenario()."""

    def test_load_ecommerce_launch_scenario(self) -> None:
        """Built-in ecommerce_launch.yaml loads correctly."""
        path = _FIXTURES_DIR / "ecommerce_launch.yaml"
        spec = load_scenario(path)

        self.assertIsInstance(spec, ScenarioSpec)
        # Roles
        self.assertIn("market_analyst", spec.roles)
        self.assertEqual(spec.roles["market_analyst"].role, "市场分析师")
        self.assertIn("pricing_specialist", spec.roles)
        self.assertEqual(spec.roles["pricing_specialist"].tools, ["calculator"])
        # Teams
        self.assertIn("hierarchical", spec.teams)
        self.assertEqual(spec.teams["hierarchical"].process, "hierarchical")
        self.assertEqual(spec.teams["hierarchical"].supervisor, "project_lead")
        # Cases
        self.assertIn("hierarchical_full_chain", spec.cases)
        self.assertEqual(spec.cases["hierarchical_full_chain"].team, "hierarchical")

    def test_nonexistent_file_raises(self) -> None:
        """Non-existent file raises FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            load_scenario("/nonexistent/path.yaml")

    def test_invalid_yaml_schema_raises(self) -> None:
        """YAML that is not a mapping raises ValueError."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("- just\n- a\n- list\n")
            f.flush()
            with self.assertRaises(ValueError):
                load_scenario(f.name)

    def test_all_four_team_types_present(self) -> None:
        """ecommerce_launch.yaml defines all 4 team process types."""
        spec = load_scenario(_FIXTURES_DIR / "ecommerce_launch.yaml")
        processes = {t.process for t in spec.teams.values()}
        self.assertEqual(processes, {"hierarchical", "sequential", "parallel", "handoff"})

    def test_all_cases_reference_valid_teams(self) -> None:
        """Every case's team key must exist in teams."""
        spec = load_scenario(_FIXTURES_DIR / "ecommerce_launch.yaml")
        for case_key, case in spec.cases.items():
            self.assertIn(
                case.team,
                spec.teams,
                f"Case {case_key!r} references unknown team {case.team!r}",
            )

    def test_all_team_members_reference_valid_roles(self) -> None:
        """Every team member key must exist in roles."""
        spec = load_scenario(_FIXTURES_DIR / "ecommerce_launch.yaml")
        for team_key, team in spec.teams.items():
            for member_key in team.members:
                self.assertIn(
                    member_key,
                    spec.roles,
                    f"Team {team_key!r} references unknown role {member_key!r}",
                )
            if team.supervisor:
                self.assertIn(
                    team.supervisor,
                    spec.roles,
                    f"Team {team_key!r} supervisor {team.supervisor!r} not in roles",
                )


class TestBuildTeam(unittest.TestCase):
    """Tests for build_team() (requires mock LLM)."""

    def test_build_sequential_team(self) -> None:
        """Sequential team builds without supervisor."""
        from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter
        from tests.support.scenario_loader import build_team

        spec = load_scenario(_FIXTURES_DIR / "ecommerce_launch.yaml")
        llm = MockLLMAdapter()
        team = build_team(spec, "sequential", llm)
        self.assertIsNotNone(team)

    def test_build_hierarchical_team(self) -> None:
        """Hierarchical team builds with supervisor."""
        from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter
        from tests.support.scenario_loader import build_team

        spec = load_scenario(_FIXTURES_DIR / "ecommerce_launch.yaml")
        llm = MockLLMAdapter()
        team = build_team(spec, "hierarchical", llm)
        self.assertIsNotNone(team)

    def test_build_parallel_team(self) -> None:
        """Parallel team builds with 3 members."""
        from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter
        from tests.support.scenario_loader import build_team

        spec = load_scenario(_FIXTURES_DIR / "ecommerce_launch.yaml")
        llm = MockLLMAdapter()
        team = build_team(spec, "parallel", llm)
        self.assertIsNotNone(team)

    def test_build_handoff_team(self) -> None:
        """Handoff team builds with 2 members."""
        from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter
        from tests.support.scenario_loader import build_team

        spec = load_scenario(_FIXTURES_DIR / "ecommerce_launch.yaml")
        llm = MockLLMAdapter()
        team = build_team(spec, "handoff", llm)
        self.assertIsNotNone(team)


if __name__ == "__main__":
    unittest.main()
