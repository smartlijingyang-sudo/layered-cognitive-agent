"""Gateway team_factory 单元测试（ADR-0052）。"""

from __future__ import annotations

import json
import unittest

from gateway.assemble import build_runnable_team, build_solo_agent
from gateway.modes import ALL_MODES
from lca.contracts.models.core.llm import LLMResponse
from lca.layer4_app.api import Agent, Team
from tests.harness.collector import InMemoryObservability
from tests.harness.scripted_llm import ScriptedLLMAdapter


class TestGatewaySoloFactory(unittest.TestCase):
    def test_solo_uses_caller_role_name(self) -> None:
        llm = ScriptedLLMAdapter({}, default_respond=True)
        agent = build_solo_agent(llm, observability=InMemoryObservability(), role="小助手")
        self.assertEqual(agent.role_profile.role, "小助手")

    def test_solo_returns_bare_agent_with_minimal_role(self) -> None:
        llm = ScriptedLLMAdapter({}, default_respond=True)
        collector = InMemoryObservability()
        agent = build_solo_agent(llm, observability=collector)
        self.assertIsInstance(agent, Agent)
        self.assertEqual(agent.role_profile.role, "助手")
        self.assertEqual(agent.role_profile.goal, "")
        self.assertEqual(agent.role_profile.backstory, "")

    def test_solo_excludes_search_skill_from_g2a_tools(self) -> None:
        llm = ScriptedLLMAdapter({}, default_respond=True)
        agent = build_solo_agent(llm, observability=InMemoryObservability())
        names = {t.name for t in agent.spec.tools}
        self.assertNotIn("search_skill", names)
        self.assertIn("web_search", names)


class TestGatewayTeamFactory(unittest.TestCase):
    def test_all_modes_are_team(self) -> None:
        self.assertEqual(ALL_MODES, ("team",))


class TestGatewayTeamCastingFactory(unittest.IsolatedAsyncioTestCase):
    """build_runnable_team：真实角色库 + 脚本化选角（ADR-0042/0052）。"""

    async def test_team_builds_team_from_role_library(self) -> None:
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
        llm = ScriptedLLMAdapter(
            {"caster": [LLMResponse(text=plan, model="scripted-llm")]}, default_respond=True
        )
        collector = InMemoryObservability()
        runnable = await build_runnable_team(
            "写一份发布方案",
            llm,
            observability=collector,
            trace_id="trace-team",
            run_id="run-team",
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
