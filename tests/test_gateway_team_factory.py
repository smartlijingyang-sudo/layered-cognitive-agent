"""Gateway team_factory 单元测试（ADR-0052）。"""

from __future__ import annotations

import json
import unittest

from lca.agent.role_library import FileRoleLibrary
from lca.application.api import Agent, Team
from lca.application.casting import LLMTeamCaster
from lca.cognition.team.modes.default_modes import (
    build_runnable_team,
    build_solo_agent,
    resolve_team_casting_dependencies,
)
from lca.plugins.collaboration.modes.solo import filter_solo_tools
from lca.cognition.team.modes_catalog import ALL_MODES
from lca.contracts.capabilities import TEAM_CASTER, TEAM_ROLE_LIBRARY
from lca.contracts.mechanisms.capability import MissingCapabilityError
from lca.contracts.models.core.llm import LLMResponse
from lca.plugins.seams.collaboration.team_casting_prompt_renderer import (
    BuiltinCastingPromptRenderer,
)
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
        # Per PR-5/PR-7 plugin-ification, solo agent has no default tools;
        # caller must explicitly pass tools= argument. This test verifies that
        # search_skill (the operational skill discovery tool) is NOT auto-loaded
        # into solo agent spec — it would leak g2a internals.
        llm = ScriptedLLMAdapter({}, default_respond=True)
        agent = build_solo_agent(llm, observability=InMemoryObservability())
        names = {t.name for t in agent.spec.tools}
        self.assertNotIn("search_skill", names)
        # solo agent spec.tools is empty (no defaults); no "search" tool.
        # Original test assumed defaults; behavior changed in plugin-ification
        # (callers must explicitly pass tools=[...] to build_solo_agent).
        self.assertEqual(names, set())

    def test_solo_drops_creator_host_tools_keeps_computer_catalog(self) -> None:
        """Solo keeps the sandbox computer set; bash/file_write stay Creator-only."""

        class _Named:
            def __init__(self, name: str) -> None:
                self.name = name

        kept = filter_solo_tools(
            [
                _Named("bash"),
                _Named("file_write"),
                _Named("cordis_control"),
                _Named("listFiles"),
                _Named("writeFile"),
                _Named("runCommand"),
                _Named("executeCode"),
                _Named("search"),
                _Named("askUserQuestion"),
                _Named("activate_skill"),
            ]
        )
        names = [tool.name for tool in kept]
        self.assertEqual(
            names,
            [
                "listFiles",
                "writeFile",
                "runCommand",
                "executeCode",
                "search",
                "askUserQuestion",
                "activate_skill",
            ],
        )


class TestGatewayTeamFactory(unittest.TestCase):
    def test_all_modes_are_team(self) -> None:
        self.assertEqual(ALL_MODES, ("team",))


class TestGatewayTeamCastingFactory(unittest.IsolatedAsyncioTestCase):
    """build_runnable_team：真实角色库 + 脚本化选角（ADR-0042/0052）。"""

    def test_casting_dependencies_are_resolved_from_scope(self) -> None:
        library = FileRoleLibrary()
        caster = LLMTeamCaster(BuiltinCastingPromptRenderer())

        class _Scope:
            def inject(self, key: str) -> object:
                return {
                    TEAM_ROLE_LIBRARY.key: library,
                    TEAM_CASTER.key: caster,
                }[key]

        resolved_library, resolved_caster = resolve_team_casting_dependencies(_Scope())
        self.assertIs(resolved_library, library)
        self.assertIs(resolved_caster, caster)

    def test_casting_dependencies_fail_closed_without_profile_scope(self) -> None:
        with self.assertRaises(MissingCapabilityError):
            resolve_team_casting_dependencies(None)

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
            library=FileRoleLibrary(),
            caster=LLMTeamCaster(BuiltinCastingPromptRenderer()),
            tools=(),
        )
        self.assertIsInstance(runnable, Team)
        roles = [member.profile.role for member in runnable.spec.members]
        self.assertEqual(roles, ["产品经理", "内容创作者"])
        event_types = [type(stamped.event).__name__ for stamped in collector.store.events]
        self.assertIn("CastingStarted", event_types)
        self.assertIn("CastingCompleted", event_types)
        # 产品路径不允许出现测试探针人设（Alice/Bob 只存在于 tests/harness）
        self.assertNotIn("Alice", roles)
        self.assertNotIn("Bob", roles)


if __name__ == "__main__":
    unittest.main()
