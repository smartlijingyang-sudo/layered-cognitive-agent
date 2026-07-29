"""SkillRouter 测试 —— 关键词路由、ModularBrain 集成、budget 无影响。"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lca.contracts.protocols import SkillRouter
from lca.contracts.state import Budget, TypedState
from lca.layer1_cognitive.brain.modular_brain import ModularBrain
from lca.layer1_cognitive.brain.skill_router import KeywordSkillRouter, StaticSkillRouter


def _make_state(task: str) -> TypedState:
    return TypedState(trace_id="test", task=task, budget=Budget())


class TestKeywordSkillRouter(unittest.IsolatedAsyncioTestCase):
    """KeywordSkillRouter 关键词匹配。"""

    async def test_matches_keyword(self) -> None:
        router = KeywordSkillRouter(
            rules={
                "research_prompt": ["研究", "调研"],
                "writing_prompt": ["写", "撰写"],
            },
        )
        state = _make_state("帮我调研一下市场趋势")
        template = await router.route(state)
        self.assertEqual(template, "research_prompt")

    async def test_matches_second_rule(self) -> None:
        router = KeywordSkillRouter(
            rules={
                "research_prompt": ["研究", "调研"],
                "writing_prompt": ["写", "撰写"],
            },
        )
        state = _make_state("请撰写一份报告")
        template = await router.route(state)
        self.assertEqual(template, "writing_prompt")

    async def test_no_match_returns_default(self) -> None:
        router = KeywordSkillRouter(
            rules={"research_prompt": ["研究"]},
            default_template="react_prompt",
        )
        state = _make_state("今天天气怎么样")
        template = await router.route(state)
        self.assertEqual(template, "react_prompt")

    async def test_case_insensitive(self) -> None:
        router = KeywordSkillRouter(
            rules={"code_prompt": ["Debug", "FIX"]},
        )
        state = _make_state("please debug this code")
        template = await router.route(state)
        self.assertEqual(template, "code_prompt")


class TestStaticSkillRouter(unittest.IsolatedAsyncioTestCase):
    """StaticSkillRouter 固定模板。"""

    async def test_always_returns_same_template(self) -> None:
        router = StaticSkillRouter("my_template")
        self.assertEqual(await router.route(_make_state("anything")), "my_template")
        self.assertEqual(await router.route(_make_state("else")), "my_template")


class TestSkillRouterProtocol(unittest.TestCase):
    """SkillRouter Protocol 结构性测试。"""

    def test_keyword_router_satisfies_protocol(self) -> None:
        router = KeywordSkillRouter(rules={})
        self.assertIsInstance(router, SkillRouter)

    def test_static_router_satisfies_protocol(self) -> None:
        router = StaticSkillRouter("t")
        self.assertIsInstance(router, SkillRouter)


class TestModularBrainWithSkillRouter(unittest.IsolatedAsyncioTestCase):
    """ModularBrain 集成 SkillRouter。"""

    async def test_think_sets_active_template(self) -> None:
        router = StaticSkillRouter("custom_prompt")

        reasoner = MagicMock()
        reasoner.generate_candidates = AsyncMock(return_value=["think aloud"])

        decision_parser = MagicMock()
        mock_decision = MagicMock()
        mock_decision.rationale = "test"
        decision_parser.parse = MagicMock(return_value=mock_decision)

        state_predictor = MagicMock()
        state_predictor.predict = AsyncMock(return_value={"next": "state"})

        state_evaluator = MagicMock()
        state_evaluator.score = AsyncMock(return_value=0.9)

        conflict_monitor = MagicMock()
        conflict_monitor.check = AsyncMock(return_value=[])

        task_coordinator = MagicMock()
        task_coordinator.arbitrate = AsyncMock(return_value=mock_decision)

        task_decomposer = MagicMock()
        task_decomposer.decompose = AsyncMock(return_value=[])

        critic = MagicMock()

        brain = ModularBrain(
            reasoner=reasoner,
            decision_parser=decision_parser,
            critic=critic,
            task_decomposer=task_decomposer,
            state_predictor=state_predictor,
            state_evaluator=state_evaluator,
            conflict_monitor=conflict_monitor,
            task_coordinator=task_coordinator,
            skill_router=router,
        )

        state = _make_state("test task")
        await brain.think(state)

        self.assertEqual(state.active_template, "custom_prompt")

    async def test_think_without_router_no_template(self) -> None:
        """无 SkillRouter 时，working_memory 不设 active_template。"""
        reasoner = MagicMock()
        reasoner.generate_candidates = AsyncMock(return_value=["think"])
        decision_parser = MagicMock()
        mock_decision = MagicMock()
        mock_decision.rationale = "test"
        decision_parser.parse = MagicMock(return_value=mock_decision)
        state_predictor = MagicMock()
        state_predictor.predict = AsyncMock(return_value={})
        state_evaluator = MagicMock()
        state_evaluator.score = AsyncMock(return_value=1.0)
        conflict_monitor = MagicMock()
        conflict_monitor.check = AsyncMock(return_value=[])
        task_coordinator = MagicMock()
        task_coordinator.arbitrate = AsyncMock(return_value=mock_decision)
        task_decomposer = MagicMock()
        task_decomposer.decompose = AsyncMock(return_value=[])
        critic = MagicMock()

        brain = ModularBrain(
            reasoner=reasoner,
            decision_parser=decision_parser,
            critic=critic,
            task_decomposer=task_decomposer,
            state_predictor=state_predictor,
            state_evaluator=state_evaluator,
            conflict_monitor=conflict_monitor,
            task_coordinator=task_coordinator,
        )

        state = _make_state("test")
        await brain.think(state)

        self.assertNotIn("active_template", state.working_memory)

    async def test_router_does_not_affect_budget(self) -> None:
        """SkillRouter 调用不应增加 budget 计数。"""
        router = StaticSkillRouter("t")

        reasoner = MagicMock()
        reasoner.generate_candidates = AsyncMock(return_value=["x"])
        decision_parser = MagicMock()
        mock_decision = MagicMock()
        mock_decision.rationale = "x"
        decision_parser.parse = MagicMock(return_value=mock_decision)
        state_predictor = MagicMock()
        state_predictor.predict = AsyncMock(return_value={})
        state_evaluator = MagicMock()
        state_evaluator.score = AsyncMock(return_value=1.0)
        conflict_monitor = MagicMock()
        conflict_monitor.check = AsyncMock(return_value=[])
        task_coordinator = MagicMock()
        task_coordinator.arbitrate = AsyncMock(return_value=mock_decision)
        task_decomposer = MagicMock()
        task_decomposer.decompose = AsyncMock(return_value=[])
        critic = MagicMock()

        brain = ModularBrain(
            reasoner=reasoner,
            decision_parser=decision_parser,
            critic=critic,
            task_decomposer=task_decomposer,
            state_predictor=state_predictor,
            state_evaluator=state_evaluator,
            conflict_monitor=conflict_monitor,
            task_coordinator=task_coordinator,
            skill_router=router,
        )

        state = _make_state("test")
        budget_before = state.budget.used_tokens
        await brain.think(state)
        budget_after = state.budget.used_tokens

        self.assertEqual(budget_before, budget_after)


if __name__ == "__main__":
    unittest.main()
