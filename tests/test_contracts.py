"""LCA Framework 单元测试 —— 验证核心契约与端到端流程。"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lca.contracts.models.core.state import AgentState, Budget


class TestBudget(unittest.TestCase):
    def test_exceeded_by_steps(self):
        budget = Budget(max_steps=5, used_steps=6)
        self.assertTrue(budget.exceeded())

    def test_not_exceeded(self):
        budget = Budget(max_steps=10, used_steps=3)
        self.assertFalse(budget.exceeded())


class TestAgentState(unittest.TestCase):
    def test_snapshot(self):
        state = AgentState(trace_id="test_trace", task="test task", budget=Budget())
        snap = state.snapshot(reason="periodic")
        self.assertEqual(snap.step, 0)
        self.assertEqual(len(state.checkpoints), 1)


class TestMockLLMAdapter(unittest.TestCase):
    def test_tool_result_response(self) -> None:
        from lca.infrastructure.llm_adapter.mock_llm import MockLLMAdapter

        llm = MockLLMAdapter()
        result = asyncio.run(
            llm.complete(
                "USER_TASK: 任意问题\nCONTEXT:\n(无历史上下文)\n",
                history=[
                    {"role": "assistant", "tool_calls": [{"id": "c1", "name": "some_tool"}]},
                    {"role": "tool", "tool_call_id": "c1", "content": "done"},
                ],
            )
        )
        self.assertIn("done", result.text)
        self.assertEqual(result.tool_calls, [])


class TestLLMStreamEventContract(unittest.TestCase):
    def test_stream_event_type_values_match_responses_sse(self) -> None:
        from lca.contracts.atoms.enums import LLMStreamEventType

        self.assertEqual(LLMStreamEventType.OUTPUT_TEXT_DELTA.value, "response.output_text.delta")
        self.assertEqual(
            LLMStreamEventType.FUNCTION_CALL_ARGUMENTS_DELTA.value,
            "response.function_call_arguments.delta",
        )
        self.assertEqual(LLMStreamEventType.COMPLETED.value, "response.completed")

    def test_stream_event_frozen_defaults(self) -> None:
        from dataclasses import FrozenInstanceError

        from lca.contracts.atoms.enums import LLMStreamEventType
        from lca.contracts.models.core.llm import LLMResponse, LLMStreamEvent

        event = LLMStreamEvent(type=LLMStreamEventType.OUTPUT_TEXT_DELTA)
        self.assertEqual(event.text, "")
        self.assertIsNone(event.tool_call_id)
        self.assertEqual(event.extra, {})
        with self.assertRaises(FrozenInstanceError):
            event.text = "x"  # type: ignore[misc]

        completed = LLMStreamEvent(
            type=LLMStreamEventType.COMPLETED,
            response=LLMResponse(text="ok"),
        )
        self.assertIsNotNone(completed.response)


if __name__ == "__main__":
    unittest.main()
