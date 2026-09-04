"""SkillRouter 测试 —— 关键词路由、ModularBrain 集成、budget 无影响。"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lca.cognition.brain.modular_brain import ModularBrain
from lca.cognition.brain.skill_router import KeywordSkillRouter, StaticSkillRouter
from lca.contracts.harness.memory.events import SkillRouted
from lca.contracts.models.core.llm import LLMResponse
from lca.contracts.models.core.state import AgentState, Budget
from lca.plugins.events.publishers._session_publish import (
    reset_publish_session,
    set_publish_session,
)
from lca.plugins.gate.decision_classifier_provider import DefaultDecisionClassifier
from lca.plugins.runtime.reducer import DefaultReducer


def _make_state(task: str) -> AgentState:
    return AgentState(trace_id="test", task=task, budget=Budget())


class _SpinePublishSession:
    """测试替身：满足 ADR-0183 fail-loud 绑定的 publish Session，丢弃 spine 信封。"""

    def append(self, payload: object, *, producer: object) -> object:
        del payload, producer
        return None


class _SpineSessionBound(unittest.IsolatedAsyncioTestCase):
    """route()/think() 的 spine 信封走 publish_via_session，须绑定 active Session。"""

    def setUp(self) -> None:
        super().setUp()
        self._publish_token = set_publish_session(_SpinePublishSession())

    def tearDown(self) -> None:
        reset_publish_session(self._publish_token)
        super().tearDown()


class _RecordingSessionSink:
    """测试替身：记录追加的 Session 事件，用于验证 skill.routed.v1 发射。"""

    def __init__(self) -> None:
        self.appended: list[tuple[object, str | None]] = []

    async def append(self, event_data, *, actor=None, **kwargs):
        del kwargs
        self.appended.append((event_data, actor))
        return event_data


class TestKeywordSkillRouter(_SpineSessionBound):
    """KeywordSkillRouter 关键词匹配。"""

    async def test_matches_keyword(self) -> None:
        router = KeywordSkillRouter(
            rules={
                "research_prompt": ["研究", "调研"],
                "writing_prompt": ["写", "撰写"],
            },
            default_template="react_prompt",
        )
        state = _make_state("调研新技术")
        name = await router.route(state)
        self.assertEqual(name, "research_prompt")

    async def test_falls_back_to_default(self) -> None:
        router = KeywordSkillRouter(
            rules={"research_prompt": ["研究"]},
            default_template="react_prompt",
        )
        state = _make_state("吃饭")
        name = await router.route(state)
        self.assertEqual(name, "react_prompt")


class TestStaticSkillRouter(_SpineSessionBound):
    """StaticSkillRouter 固定返回。"""

    async def test_always_returns_same(self) -> None:
        router = StaticSkillRouter("custom_prompt")
        state = _make_state("anything")
        self.assertEqual(await router.route(state), "custom_prompt")


class TestSkillRouterIntegration(_SpineSessionBound):
    """ModularBrain + SkillRouter 集成。"""

    async def test_router_sets_active_template(self) -> None:
        router = StaticSkillRouter("custom_prompt")

        reasoner = MagicMock()
        reasoner.generate_thoughts = AsyncMock(return_value=LLMResponse(text="think"))
        mock_decision = MagicMock()
        mock_decision.rationale = "test"

        critic = MagicMock()

        brain = ModularBrain(
            reasoner=reasoner,
            reducer=DefaultReducer(),
            classifier=DefaultDecisionClassifier(),
            critic=critic,
            skill_router=router,
        )

        state = _make_state("test task")
        await brain.think(state)

        self.assertEqual(state.active_template, "custom_prompt")

    async def test_router_requires_explicit_reducer(self) -> None:
        """SkillRouter writes state, so it cannot use a hidden local Reducer."""
        reasoner = MagicMock()
        reasoner.generate_thoughts = AsyncMock(return_value=LLMResponse(text="think"))
        brain = ModularBrain(
            reasoner=reasoner,
            classifier=DefaultDecisionClassifier(),
            skill_router=StaticSkillRouter("custom_prompt"),
        )

        with self.assertRaisesRegex(RuntimeError, "requires Reducer"):
            await brain.think(_make_state("test task"))

    async def test_think_without_router_no_template(self) -> None:
        """无 SkillRouter 时，working_memory 不设 active_template。"""
        reasoner = MagicMock()
        reasoner.generate_thoughts = AsyncMock(return_value=LLMResponse(text="think"))
        mock_decision = MagicMock()
        mock_decision.rationale = "test"

        critic = MagicMock()

        brain = ModularBrain(
            reasoner=reasoner,
            reducer=DefaultReducer(),
            classifier=DefaultDecisionClassifier(),
            critic=critic,
        )

        state = _make_state("test")
        await brain.think(state)

        self.assertNotIn("active_template", state.working_memory)

    async def test_router_does_not_affect_budget(self) -> None:
        """SkillRouter 调用不应增加 budget 计数。"""
        router = StaticSkillRouter("t")

        reasoner = MagicMock()
        reasoner.generate_thoughts = AsyncMock(return_value=LLMResponse(text="x"))
        mock_decision = MagicMock()
        mock_decision.rationale = "x"

        critic = MagicMock()

        brain = ModularBrain(
            reasoner=reasoner,
            reducer=DefaultReducer(),
            classifier=DefaultDecisionClassifier(),
            critic=critic,
            skill_router=router,
        )

        state = _make_state("test")
        budget_before = state.budget.used_tokens
        await brain.think(state)
        budget_after = state.budget.used_tokens

        self.assertEqual(budget_before, budget_after)


class TestSkillRouterSessionEmission(_SpineSessionBound):
    """注入可选 Session sink 时，成功路由追加 skill.routed.v1 事实。"""

    async def test_keyword_match_emits_skill_routed(self) -> None:
        sink = _RecordingSessionSink()
        router = KeywordSkillRouter(
            rules={"research_prompt": ["调研"]},
            default_template="react_prompt",
            session_events=sink,
        )
        name = await router.route(_make_state("调研新技术"))
        self.assertEqual(name, "research_prompt")
        self.assertEqual(len(sink.appended), 1)
        event, actor = sink.appended[0]
        assert isinstance(event, SkillRouted)
        self.assertEqual(event.template_id, "research_prompt")
        self.assertEqual(event.decision_path, "keyword_match")
        self.assertEqual(event.source, "skill_router")
        self.assertEqual(actor, "system")

    async def test_keyword_default_emits_skill_routed(self) -> None:
        sink = _RecordingSessionSink()
        router = KeywordSkillRouter(
            rules={"research_prompt": ["研究"]},
            default_template="react_prompt",
            session_events=sink,
        )
        name = await router.route(_make_state("吃饭"))
        self.assertEqual(name, "react_prompt")
        event, _ = sink.appended[0]
        assert isinstance(event, SkillRouted)
        self.assertEqual(event.template_id, "react_prompt")
        self.assertEqual(event.decision_path, "keyword_default")

    async def test_static_router_emits_skill_routed(self) -> None:
        sink = _RecordingSessionSink()
        router = StaticSkillRouter("custom_prompt", session_events=sink)
        self.assertEqual(await router.route(_make_state("anything")), "custom_prompt")
        self.assertEqual(len(sink.appended), 1)
        event, actor = sink.appended[0]
        assert isinstance(event, SkillRouted)
        self.assertEqual(event.template_id, "custom_prompt")
        self.assertEqual(event.decision_path, "static")
        self.assertEqual(actor, "system")

    async def test_without_sink_route_still_succeeds(self) -> None:
        router = KeywordSkillRouter(
            rules={"research_prompt": ["调研"]}, default_template="react_prompt"
        )
        self.assertEqual(await router.route(_make_state("调研新技术")), "research_prompt")


if __name__ == "__main__":
    unittest.main()
