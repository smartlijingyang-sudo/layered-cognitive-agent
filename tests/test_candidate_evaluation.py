"""CandidateEvaluationPipeline 评估行为测试 —— 验证置信度选优与冲突可见性。"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lca.contracts.atoms.semantic_keys import EVAL_CONFLICTS
from lca.contracts.models.core.decision import Decision
from lca.contracts.models.core.state import AgentState, Budget
from lca.layer1_cognitive.brain.candidate_evaluation_pipeline import (
    SimpleCandidateEvaluationPipeline,
)


def _make_decision(
    decision_id: str,
    confidence: float,
    *,
    action_type: str = "respond",
    rationale: str = "test",
    response_text: str | None = None,
) -> Decision:
    return Decision(
        decision_id=decision_id,
        action_type=action_type,
        rationale=rationale,
        confidence=confidence,
        response_text=response_text,
    )


def _make_state() -> AgentState:
    return AgentState(trace_id="t", task="test", budget=Budget())


class TestConfidenceBasedSelection(unittest.IsolatedAsyncioTestCase):
    """evaluate 应选置信度最高的候选，而非第一个。"""

    async def test_highest_confidence_wins(self) -> None:
        candidates = [
            _make_decision("d1", 0.3),
            _make_decision("d2", 0.9),
            _make_decision("d3", 0.5),
        ]
        pipeline = SimpleCandidateEvaluationPipeline()
        best = await pipeline.evaluate(_make_state(), candidates)
        self.assertEqual(best.decision_id, "d2")

    async def test_first_wins_on_tie(self) -> None:
        candidates = [
            _make_decision("d1", 0.8),
            _make_decision("d2", 0.8),
        ]
        pipeline = SimpleCandidateEvaluationPipeline()
        best = await pipeline.evaluate(_make_state(), candidates)
        self.assertEqual(best.decision_id, "d1")

    async def test_single_candidate_returned(self) -> None:
        candidates = [_make_decision("only", 0.1)]
        pipeline = SimpleCandidateEvaluationPipeline()
        best = await pipeline.evaluate(_make_state(), candidates)
        self.assertEqual(best.decision_id, "only")


class TestConflictPropagation(unittest.IsolatedAsyncioTestCase):
    """冲突检测结果应写入 best.extra，而非只进日志。"""

    async def test_content_conflict_written_to_extra(self) -> None:
        candidates = [
            _make_decision("d1", 0.9, response_text="answer A"),
            _make_decision("d2", 0.5, response_text="answer B"),
        ]
        pipeline = SimpleCandidateEvaluationPipeline()
        best = await pipeline.evaluate(_make_state(), candidates)
        self.assertIn(EVAL_CONFLICTS, best.extra)
        self.assertIn("content_disagreement", best.extra[EVAL_CONFLICTS])

    async def test_action_type_conflict_written_to_extra(self) -> None:
        candidates = [
            _make_decision("d1", 0.9, action_type="respond", response_text="same"),
            _make_decision("d2", 0.5, action_type="delegate", response_text="same"),
        ]
        pipeline = SimpleCandidateEvaluationPipeline()
        best = await pipeline.evaluate(_make_state(), candidates)
        self.assertIn(EVAL_CONFLICTS, best.extra)
        self.assertIn("action_type_disagreement", best.extra[EVAL_CONFLICTS])

    async def test_no_conflict_no_extra_key(self) -> None:
        candidates = [
            _make_decision("d1", 0.9, response_text="same answer"),
            _make_decision("d2", 0.5, response_text="same answer"),
        ]
        pipeline = SimpleCandidateEvaluationPipeline()
        best = await pipeline.evaluate(_make_state(), candidates)
        self.assertNotIn(EVAL_CONFLICTS, best.extra)

    async def test_single_candidate_no_conflict(self) -> None:
        candidates = [_make_decision("only", 0.7)]
        pipeline = SimpleCandidateEvaluationPipeline()
        best = await pipeline.evaluate(_make_state(), candidates)
        self.assertNotIn(EVAL_CONFLICTS, best.extra)


class TestDecompose(unittest.IsolatedAsyncioTestCase):
    """decompose 默认返回原始任务。"""

    async def test_decompose_returns_task(self) -> None:
        state = _make_state()
        pipeline = SimpleCandidateEvaluationPipeline()
        subtasks = await pipeline.decompose(state)
        self.assertEqual(subtasks, ["test"])


if __name__ == "__main__":
    unittest.main()
