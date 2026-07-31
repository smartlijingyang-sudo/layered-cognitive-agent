"""ParallelStrategy + Synthesizer 聚合测试 —— 验证 MoA fan-in 不再静默丢数据。"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lca.contracts.lifecycle import TaskStatus
from lca.contracts.protocols import Synthesizer, TeamContext
from lca.contracts.result import Result
from lca.contracts.state import Budget
from lca.layer1_cognitive.brain.synthesizer import ConcatSynthesizer
from lca.layer3_agent.orchestration_strategies import ParallelStrategy


def _make_result(
    trace_id: str,
    output: str,
    status: TaskStatus = TaskStatus.COMPLETED,
    steps: int = 1,
    tokens: int = 10,
) -> Result:
    return Result(
        trace_id=trace_id,
        status=status,
        final_state_ref="",
        total_steps=steps,
        budget_used=Budget(used_tokens=tokens, used_steps=steps),
        output=output,
    )


class _FakeMember:
    """模拟 AgentUnit，run 返回预设 Result。"""

    def __init__(self, result: Result) -> None:
        self._result = result

    async def run(self, task: str) -> Result:
        return self._result


class TestConcatSynthesizer(unittest.IsolatedAsyncioTestCase):
    """ConcatSynthesizer 单元测试。"""

    async def test_synthesize_combines_all_outputs(self) -> None:
        """聚合结果必须包含所有候选的输出，而非只取最后一个。"""
        synth = ConcatSynthesizer()
        candidates = [
            _make_result("t1", "Answer from Agent 1"),
            _make_result("t2", "Answer from Agent 2"),
            _make_result("t3", "Answer from Agent 3"),
        ]

        result = await synth.synthesize("test objective", candidates)

        self.assertEqual(result.status, "completed")
        assert result.output is not None
        self.assertIn("Answer from Agent 1", result.output)
        self.assertIn("Answer from Agent 2", result.output)
        self.assertIn("Answer from Agent 3", result.output)

    async def test_synthesize_aggregates_budget(self) -> None:
        """聚合结果的 budget 应是所有候选的总和。"""
        synth = ConcatSynthesizer()
        candidates = [
            _make_result("t1", "a", tokens=10, steps=2),
            _make_result("t2", "b", tokens=20, steps=3),
        ]

        result = await synth.synthesize("obj", candidates)

        self.assertEqual(result.total_steps, 5)
        self.assertEqual(result.budget_used.used_tokens, 30)
        self.assertEqual(result.budget_used.used_steps, 5)

    async def test_synthesize_empty_candidates(self) -> None:
        """空候选列表应返回 failed 状态。"""
        synth = ConcatSynthesizer()
        result = await synth.synthesize("obj", [])

        self.assertEqual(result.status, "failed")
        self.assertIn("No candidates", result.error or "")

    async def test_synthesize_all_failed(self) -> None:
        """所有候选都失败时，聚合结果也应为 failed。"""
        synth = ConcatSynthesizer()
        candidates = [
            _make_result("t1", "", status=TaskStatus.FAILED),
            _make_result("t2", "", status=TaskStatus.FAILED),
        ]

        result = await synth.synthesize("obj", candidates)

        self.assertEqual(result.status, "failed")

    async def test_synthesize_partial_success(self) -> None:
        """部分候选成功时，聚合结果应为 completed（至少有一个成功）。"""
        synth = ConcatSynthesizer()
        candidates = [
            _make_result("t1", "good output", status=TaskStatus.COMPLETED),
            _make_result("t2", "", status=TaskStatus.FAILED),
        ]

        result = await synth.synthesize("obj", candidates)

        self.assertEqual(result.status, "completed")
        assert result.output is not None
        self.assertIn("good output", result.output)

    async def test_synthesize_collects_lessons(self) -> None:
        """聚合结果应收集所有候选的 lessons。"""
        synth = ConcatSynthesizer()
        c1 = _make_result("t1", "a")
        c1.lessons = ["lesson1"]
        c2 = _make_result("t2", "b")
        c2.lessons = ["lesson2", "lesson3"]

        result = await synth.synthesize("obj", [c1, c2])

        self.assertEqual(result.lessons, ["lesson1", "lesson2", "lesson3"])

    async def test_custom_separator(self) -> None:
        """自定义分隔符应生效。"""
        synth = ConcatSynthesizer(separator=" | ")
        candidates = [
            _make_result("t1", "A"),
            _make_result("t2", "B"),
        ]

        result = await synth.synthesize("obj", candidates)

        assert result.output is not None
        self.assertIn(" | ", result.output)

    async def test_extra_metadata(self) -> None:
        """聚合结果的 extra 应包含合成方法和候选数量。"""
        synth = ConcatSynthesizer()
        candidates = [_make_result("t1", "a"), _make_result("t2", "b")]

        result = await synth.synthesize("obj", candidates)

        self.assertEqual(result.extra["synthesis_method"], "concat")
        self.assertEqual(result.extra["candidate_count"], 2)


class TestParallelStrategyWithSynthesizer(unittest.IsolatedAsyncioTestCase):
    """ParallelStrategy 集成 Synthesizer 的端到端测试。"""

    async def test_parallel_with_synthesizer_aggregates(self) -> None:
        """ParallelStrategy + ConcatSynthesizer 应聚合所有成员输出。"""
        members = [
            _FakeMember(_make_result("t1", "Result A")),
            _FakeMember(_make_result("t2", "Result B")),
            _FakeMember(_make_result("t3", "Result C")),
        ]
        context = TeamContext(members=members)
        strategy = ParallelStrategy(synthesizer=ConcatSynthesizer())

        result = await strategy.run(context, "test task")

        self.assertEqual(result.status, "completed")
        assert result.output is not None
        self.assertIn("Result A", result.output)
        self.assertIn("Result B", result.output)
        self.assertIn("Result C", result.output)

    async def test_parallel_without_synthesizer_returns_last(self) -> None:
        """无 Synthesizer 时保持向后兼容：返回最后一个结果。"""
        members = [
            _FakeMember(_make_result("t1", "Result A")),
            _FakeMember(_make_result("t2", "Result B")),
        ]
        context = TeamContext(members=members)
        strategy = ParallelStrategy()

        result = await strategy.run(context, "test task")

        self.assertEqual(result.output, "Result B")

    async def test_parallel_empty_members(self) -> None:
        """空成员列表应返回 failed。"""
        context = TeamContext(members=[])
        strategy = ParallelStrategy(synthesizer=ConcatSynthesizer())

        result = await strategy.run(context, "test task")

        self.assertEqual(result.status, "failed")


class TestSynthesizerProtocol(unittest.IsolatedAsyncioTestCase):
    """Synthesizer Protocol 结构性测试。"""

    def test_concat_synthesizer_satisfies_protocol(self) -> None:
        """ConcatSynthesizer 应满足 Synthesizer Protocol。"""
        synth = ConcatSynthesizer()
        self.assertIsInstance(synth, Synthesizer)

    async def test_custom_synthesizer(self) -> None:
        """自定义 Synthesizer 实现应可插入 ParallelStrategy。"""

        class FirstResultSynthesizer:
            """总是返回第一个候选的 Synthesizer（测试可插拔性）。"""

            async def synthesize(self, objective: str, candidates: list[Result]) -> Result:
                return candidates[0]

        first_synth = FirstResultSynthesizer()
        self.assertIsInstance(first_synth, Synthesizer)

        members = [
            _FakeMember(_make_result("t1", "First")),
            _FakeMember(_make_result("t2", "Second")),
        ]
        context = TeamContext(members=members)
        # 测试用内部类满足 Synthesizer Protocol 但 mypy 无法推断结构子类型
        strategy = ParallelStrategy(synthesizer=first_synth)  # type: ignore[arg-type]

        result = await strategy.run(context, "test")

        self.assertEqual(result.output, "First")


if __name__ == "__main__":
    unittest.main()
