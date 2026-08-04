"""Step 3 单元测试：Reasoner prompt 委派感知 + DecisionParser delegate 分支。"""

from __future__ import annotations

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lca.contracts.agent_spec import DEFAULT_DELEGATE_MAX_ATTEMPTS
from lca.contracts.role_team import RoleProfile, ToolPermissionManifest
from lca.contracts.state import AgentState, Budget
from lca.contracts.team_awareness import Settlement, TeamAwareness
from lca.layer1_cognitive.brain.decision_parser import SimpleDecisionParser
from lca.layer1_cognitive.brain.prompts import load_builtin_prompt
from lca.layer1_cognitive.brain.reasoner import (
    PromptReasoner,
    build_teammates_text,
)
from lca.layer1_cognitive.member_status import InMemoryMemberStatus


def _make_state(
    task: str = "test task",
    teammates: list[RoleProfile] | None = None,
    *,
    as_lead: bool = False,
) -> AgentState:
    awareness = None
    if as_lead:
        roles = tuple(p.role for p in (teammates or [])) or ("member",)
        awareness = TeamAwareness(
            teammates=list(teammates or []),
            settlement=Settlement(
                member_status=InMemoryMemberStatus(role_order=roles),
                max_attempts=DEFAULT_DELEGATE_MAX_ATTEMPTS,
            ),
        )
    return AgentState(
        trace_id="test-trace",
        task=task,
        budget=Budget(),
        team_awareness=awareness,
    )


def _empty_manifest() -> ToolPermissionManifest:
    return ToolPermissionManifest(allowed_tools=[])


def _make_profile(role: str = "supervisor", goal: str = "coordinate") -> RoleProfile:
    return RoleProfile(
        role=role, goal=goal, backstory="test", tool_permission_manifest=_empty_manifest()
    )


class TestBuildTeamRoster(unittest.TestCase):
    """build_teammates_text 工具函数。"""

    def test_empty_list(self) -> None:
        self.assertEqual(build_teammates_text([]), "(无可用队友)")

    def test_single_profile(self) -> None:
        profiles = [_make_profile("researcher", "research topics")]
        result = build_teammates_text(profiles)
        self.assertIn("researcher", result)
        self.assertIn("research topics", result)

    def test_multiple_profiles(self) -> None:
        profiles = [
            _make_profile("researcher", "research"),
            _make_profile("writer", "write reports"),
        ]
        result = build_teammates_text(profiles)
        self.assertIn("researcher", result)
        self.assertIn("writer", result)
        self.assertEqual(result.count("\n") + 1, 2)


class TestDecisionParserDelegate(unittest.TestCase):
    """SimpleDecisionParser.parse() 的 delegate 分支。"""

    def setUp(self) -> None:
        self.parser = SimpleDecisionParser()

    def test_delegate_produces_delegation_spec(self) -> None:
        raw = json.dumps(
            {
                "action_type": "delegate",
                "target_role": "researcher",
                "subtask": "分析竞品数据",
                "rationale": "researcher 更擅长数据分析",
                "confidence": 0.9,
            }
        )
        decision = self.parser.parse(raw, _make_state())
        self.assertEqual(decision.action_type, "delegate")
        self.assertTrue(decision.delegations)
        self.assertEqual(decision.delegations[0].target_role, "researcher")
        self.assertEqual(decision.delegations[0].subtask, "分析竞品数据")
        self.assertEqual(decision.rationale, "researcher 更擅长数据分析")
        self.assertAlmostEqual(decision.confidence, 0.9)

    def test_delegate_with_context_refs(self) -> None:
        raw = json.dumps(
            {
                "action_type": "delegate",
                "target_role": "analyst",
                "subtask": "总结文档",
                "context_refs": ["ctx://doc/1", "ctx://doc/2"],
                "rationale": "需要总结",
                "confidence": 0.8,
            }
        )
        decision = self.parser.parse(raw, _make_state())
        self.assertEqual(decision.delegations[0].context_refs, ["ctx://doc/1", "ctx://doc/2"])

    def test_delegate_without_target_role(self) -> None:
        raw = json.dumps(
            {
                "action_type": "delegate",
                "subtask": "做点什么",
                "rationale": "test",
                "confidence": 0.5,
            }
        )
        decision = self.parser.parse(raw, _make_state())
        self.assertEqual(decision.action_type, "delegate")
        self.assertIsNone(decision.delegations[0].target_role)
        self.assertEqual(decision.delegations[0].subtask, "做点什么")

    def test_delegate_with_markdown_code_block(self) -> None:
        raw = (
            "```json\n"
            + json.dumps(
                {
                    "action_type": "delegate",
                    "target_role": "coder",
                    "subtask": "写代码",
                    "rationale": "coder 负责",
                    "confidence": 0.7,
                }
            )
            + "\n```"
        )
        decision = self.parser.parse(raw, _make_state())
        self.assertEqual(decision.action_type, "delegate")
        self.assertTrue(decision.delegations)
        self.assertEqual(decision.delegations[0].target_role, "coder")

    def test_use_tool_still_works(self) -> None:
        raw = json.dumps(
            {
                "action_type": "use_tool",
                "tool_name": "search",
                "arguments": {"query": "test"},
                "rationale": "需要搜索",
                "confidence": 0.8,
            }
        )
        decision = self.parser.parse(raw, _make_state())
        self.assertEqual(decision.action_type, "use_tool")
        self.assertEqual(decision.delegations, [])
        self.assertEqual(len(decision.tool_calls), 1)
        self.assertEqual(decision.tool_calls[0].tool_name, "search")

    def test_respond_still_works(self) -> None:
        raw = json.dumps(
            {
                "action_type": "respond",
                "response_text": "这是回复",
                "rationale": "直接回答",
                "confidence": 1.0,
            }
        )
        decision = self.parser.parse(raw, _make_state())
        self.assertEqual(decision.action_type, "respond")
        self.assertEqual(decision.delegations, [])
        self.assertEqual(decision.response_text, "这是回复")

    def test_delegate_context_refs_non_list_coerced(self) -> None:
        raw = json.dumps(
            {
                "action_type": "delegate",
                "target_role": "worker",
                "subtask": "处理",
                "context_refs": "single-ref",
                "rationale": "test",
                "confidence": 0.5,
            }
        )
        decision = self.parser.parse(raw, _make_state())
        self.assertEqual(decision.delegations[0].context_refs, ["single-ref"])


class TestReasonerTeamRoster(unittest.IsolatedAsyncioTestCase):
    """PromptReasoner 单一实现：无 awareness 走 react，有 awareness 走层级提示词。"""

    async def test_solo_reasoner_uses_react_prompt(self) -> None:
        captured_prompt: list[str] = []

        class FakeLLM:
            async def complete(self, prompt: str, **kwargs):
                captured_prompt.append(prompt)
                return '{"action_type": "respond", "response_text": "ok", "rationale": "", "confidence": 1.0}'

        reasoner = PromptReasoner(
            FakeLLM(),
            _make_profile(),
            "search()",
            templates={
                "react_prompt": "ROLE: {role}\nTASK: {task}\nTOOLS: {tools}\nCONTEXT:\n{context}"
            },
        )
        await reasoner.generate_thoughts(_make_state())

        self.assertEqual(len(captured_prompt), 1)
        self.assertNotIn("TEAM_ROSTER", captured_prompt[0])
        self.assertIn("ROLE: supervisor", captured_prompt[0])

    async def test_lead_reasoner_uses_hierarchical_prompt(self) -> None:
        captured_prompt: list[str] = []

        class FakeLLM:
            async def complete(self, prompt: str, **kwargs):
                captured_prompt.append(prompt)
                return '{"action_type": "delegate", "target_role": "researcher", "subtask": "分析", "rationale": "test", "confidence": 0.8}'

        teammates = [
            RoleProfile(
                role="researcher",
                goal="research topics",
                backstory="",
                tool_permission_manifest=_empty_manifest(),
            ),
            RoleProfile(
                role="writer",
                goal="write reports",
                backstory="",
                tool_permission_manifest=_empty_manifest(),
            ),
        ]
        reasoner = PromptReasoner(
            FakeLLM(),
            _make_profile(),
            "search()",
            templates={
                "react_prompt": "SHOULD NOT BE USED",
                "hierarchical_prompt": load_builtin_prompt("hierarchical_prompt"),
            },
        )
        await reasoner.generate_thoughts(_make_state(teammates=teammates, as_lead=True))

        self.assertEqual(len(captured_prompt), 1)
        prompt = captured_prompt[0]
        self.assertIn("TEAMMATES", prompt)
        self.assertIn("researcher", prompt)
        self.assertIn("writer", prompt)
        self.assertIn("delegate", prompt)
        self.assertIn("target_role", prompt)
        self.assertIn("subtask", prompt)
        self.assertNotIn("SHOULD NOT BE USED", prompt)

    async def test_hierarchical_prompt_has_allowed_actions_placeholder(self) -> None:
        """确保 hierarchical 模板包含 {allowed_actions} 占位符，由 Reasoner 从 Registry 动态注入。"""
        template = load_builtin_prompt("hierarchical_prompt")
        self.assertIn("{allowed_actions}", template)
        self.assertIn("delegate", template)
        self.assertIn("target_role", template)
        self.assertIn("subtask", template)


if __name__ == "__main__":
    unittest.main()
