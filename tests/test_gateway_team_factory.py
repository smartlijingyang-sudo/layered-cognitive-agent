"""Gateway team_factory 单元测试。"""

from __future__ import annotations

import json
import unittest

from gateway.mode_catalog import ALL_MODES, get_mode_definition
from gateway.team_factory import build_runnable, build_runnable_auto
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


class TestGatewayAutoFactory(unittest.IsolatedAsyncioTestCase):
    """build_runnable_auto：真实角色库 + 脚本化选角（ADR-0042）。"""

    async def test_auto_builds_team_from_role_library(self) -> None:
        plan = json.dumps(
            {
                "selected": [
                    {"role_id": "product/product-manager", "task_hint": "输出需求要点"},
                    {"role_id": "marketing/marketing-content-creator"},
                ],
                "governance": {"kind": "pipeline"},
                "rationale": "先产品后内容",
            },
            ensure_ascii=False,
        )
        llm = ScriptedLLMAdapter({"caster": [plan]}, default_respond=True)
        collector = InMemoryObservability()
        runnable = await build_runnable_auto(
            "写一份发布方案",
            llm,
            observability=collector,
            trace_id="trace-auto",
            run_id="run-auto",
        )
        self.assertIsInstance(runnable, Team)
        roles = [member.profile.role for member in runnable.spec.members]
        self.assertEqual(roles, ["产品经理", "内容创作者"])
        event_types = [type(stamped.event).__name__ for stamped in collector.journal.events]
        self.assertIn("CastingStarted", event_types)
        self.assertIn("CastingCompleted", event_types)
        # 产品路径不允许出现测试探针人设（Alice/Bob 只存在于 tests/harness）
        self.assertNotIn("Alice", roles)
        self.assertNotIn("Bob", roles)


if __name__ == "__main__":
    unittest.main()
