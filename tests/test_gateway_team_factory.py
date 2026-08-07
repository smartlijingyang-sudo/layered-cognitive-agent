"""Gateway team_factory 单元测试。"""

from __future__ import annotations

import unittest

from gateway.mode_catalog import ALL_MODES, get_mode_definition
from gateway.team_factory import build_runnable
from lca.layer4_app.api import Agent, Team
from tests.harness.collector import InMemoryObservability
from tests.harness.scripted_llm import ScriptedLLMAdapter, respond


class TestGatewayTeamFactory(unittest.TestCase):
    def test_all_modes_build_without_probe_names(self) -> None:
        llm = ScriptedLLMAdapter({"独立分析师": [respond("ok")]}, default_respond=True)
        collector = InMemoryObservability()
        for mode in ALL_MODES:
            with self.subTest(mode=mode):
                runnable = build_runnable(mode, llm, observability=collector)
                if mode == "solo":
                    self.assertIsInstance(runnable, Agent)
                    self.assertEqual(runnable.role_profile.role, "独立分析师")
                else:
                    self.assertIsInstance(runnable, Team)
                    roles = {m.profile.role for m in runnable.spec.members}
                    self.assertNotIn("Alice", roles)
                    self.assertNotIn("Bob", roles)

    def test_board_mode_has_lead_and_two_members(self) -> None:
        definition = get_mode_definition("board")
        self.assertTrue(definition.has_lead)
        self.assertEqual(len(definition.member_roles), 2)


if __name__ == "__main__":
    unittest.main()
