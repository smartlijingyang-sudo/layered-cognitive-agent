"""Step 3 单元测试：Reasoner prompt 委派感知 + DecisionParser delegate 分支。"""

from __future__ import annotations

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lca.contracts.role_team import RoleProfile, ToolPermissionManifest
from lca.contracts.state import Budget, TypedState
from lca.layer1_cognitive.brain.decision_parser import SimpleDecisionParser
from lca.layer1_cognitive.brain.reasoner import (
    HIERARCHICAL_DELEGATE_TEMPLATE,
    SimpleReasoner,
    build_team_roster,
)
from lca.layer1_cognitive.prompt_manager import SimplePromptManager


def _make_state(task: str = "test task") -> TypedState:
    return TypedState(trace_id="test-trace", task=task, budget=Budget())


def _empty_manifest() -> ToolPermissionManifest:
    return ToolPermissionManifest(allowed_tools=[])


def _make_profile(role: str = "supervisor", goal: str = "coordinate") -> RoleProfile:
    return RoleProfile(
        role=role, goal=goal, backstory="test", tool_permission_manifest=_empty_manifest()
    )


class TestBuildTeamRoster(unittest.TestCase):
    """build_team_roster 工具函数。"""

    def test_empty_list(self) -> None:
        self.assertEqual(build_team_roster([]), "(无可用队友)")

    def test_single_profile(self) -> None:
        profiles = [_make_profile("researcher", "research topics")]
        result = build_team_roster(profiles)
        self.assertIn("researcher", result)
        self.assertIn("research topics", result)

    def test_multiple_profiles(self) -> None:
        profiles = [
            _make_profile("researcher", "research"),
            _make_profile("writer", "write reports"),
        ]
        result = build_team_roster(profiles)
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
        self.assertIsNotNone(decision.delegate_to)
        self.assertEqual(decision.delegate_to.target_role, "researcher")
        self.assertEqual(decision.delegate_to.subtask, "分析竞品数据")
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
        self.assertEqual(decision.delegate_to.context_refs, ["ctx://doc/1", "ctx://doc/2"])

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
        self.assertIsNone(decision.delegate_to.target_role)
        self.assertEqual(decision.delegate_to.subtask, "做点什么")

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
        self.assertIsNotNone(decision.delegate_to)
        self.assertEqual(decision.delegate_to.target_role, "coder")

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
        self.assertIsNone(decision.delegate_to)
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
        self.assertIsNone(decision.delegate_to)
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
        self.assertEqual(decision.delegate_to.context_refs, ["single-ref"])


class TestReasonerTeamRoster(unittest.IsolatedAsyncioTestCase):
    """SimpleReasoner：team_roster 存在时使用 hierarchical_prompt 模板。"""

    async def test_without_roster_uses_react_prompt(self) -> None:
        captured_prompt: list[str] = []

        class FakeLLM:
            async def complete(self, prompt: str, **kwargs):
                captured_prompt.append(prompt)
                return '{"action_type": "respond", "response_text": "ok", "rationale": "", "confidence": 1.0}'

        pm = SimplePromptManager()
        pm.register_template(
            "react_prompt", "ROLE: {role}\nTASK: {task}\nTOOLS: {tools}\nCONTEXT:\n{context}"
        )

        reasoner = SimpleReasoner(FakeLLM(), pm, _make_profile(), "search()", team_roster=None)
        await reasoner.generate_candidates(_make_state())

        self.assertEqual(len(captured_prompt), 1)
        self.assertNotIn("TEAM_ROSTER", captured_prompt[0])
        self.assertIn("ROLE: supervisor", captured_prompt[0])

    async def test_with_roster_uses_hierarchical_prompt(self) -> None:
        captured_prompt: list[str] = []

        class FakeLLM:
            async def complete(self, prompt: str, **kwargs):
                captured_prompt.append(prompt)
                return '{"action_type": "delegate", "target_role": "researcher", "subtask": "分析", "rationale": "test", "confidence": 0.8}'

        pm = SimplePromptManager()
        pm.register_template("react_prompt", "SHOULD NOT BE USED")
        pm.register_template("hierarchical_prompt", HIERARCHICAL_DELEGATE_TEMPLATE)

        roster = "- role: researcher | goal: research topics\n- role: writer | goal: write reports"
        reasoner = SimpleReasoner(FakeLLM(), pm, _make_profile(), "search()", team_roster=roster)
        await reasoner.generate_candidates(_make_state())

        self.assertEqual(len(captured_prompt), 1)
        prompt = captured_prompt[0]
        self.assertIn("TEAM_ROSTER", prompt)
        self.assertIn("researcher", prompt)
        self.assertIn("writer", prompt)
        self.assertIn("delegate", prompt)
        self.assertIn("target_role", prompt)
        self.assertIn("subtask", prompt)
        self.assertNotIn("SHOULD NOT BE USED", prompt)

    async def test_hierarchical_prompt_has_allowed_actions_placeholder(self) -> None:
        """确保 hierarchical 模板包含 {allowed_actions} 占位符，由 Reasoner 从 Registry 动态注入。"""
        self.assertIn("{allowed_actions}", HIERARCHICAL_DELEGATE_TEMPLATE)
        self.assertIn("delegate", HIERARCHICAL_DELEGATE_TEMPLATE)
        self.assertIn("target_role", HIERARCHICAL_DELEGATE_TEMPLATE)
        self.assertIn("subtask", HIERARCHICAL_DELEGATE_TEMPLATE)


if __name__ == "__main__":
    unittest.main()
