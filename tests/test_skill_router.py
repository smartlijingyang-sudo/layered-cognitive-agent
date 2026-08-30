"""SkillRouter 测试 —— 关键词路由、ModularBrain 集成、budget 无影响。"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lca.contracts.models.core.llm import LLMResponse
from lca.contracts.models.core.state import AgentState, Budget
from lca.cognition.brain.modular_brain import ModularBrain
from lca.cognition.brain.skill_router import KeywordSkillRouter, StaticSkillRouter
from lca.layer2_runtime.reducer import DefaultReducer
from lca.plugins.providers.decision_classifier import DefaultDecisionClassifier


def _make_state(task: str) -> AgentState:
    return AgentState(trace_id="test", task=task, budget=Budget())


class TestKeywordSkillRouter(unittest.IsolatedAsyncioTestCase):
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


class TestStaticSkillRouter(unittest.IsolatedAsyncioTestCase):
    """StaticSkillRouter 固定返回。"""

    async def test_always_returns_same(self) -> None:
        router = StaticSkillRouter("custom_prompt")
        state = _make_state("anything")
        self.assertEqual(await router.route(state), "custom_prompt")


class TestSkillRouterIntegration(unittest.IsolatedAsyncioTestCase):
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


if __name__ == "__main__":
    unittest.main()
