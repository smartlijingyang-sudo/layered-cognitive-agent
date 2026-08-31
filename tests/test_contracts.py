"""LCA Framework 单元测试 —— 验证核心契约与端到端流程。"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lca.contracts.models.core.state import AgentState, Budget
from lca.infrastructure.llm_adapter.mock_llm import MockLLMAdapter
from lca.infrastructure.tools.calculator import build_tools as build_calculator_tools


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


class TestCalculatorTool(unittest.TestCase):
    def test_simple_arithmetic(self):
        tool = build_calculator_tools()[0]
        result = asyncio.run(tool.execute({"expression": "2 + 3 * 4"}))
        self.assertTrue(result.success)
        self.assertEqual(result.payload, 14)

    def test_invalid_expression(self):
        tool = build_calculator_tools()[0]
        result = asyncio.run(tool.execute({"expression": "import os"}))
        self.assertFalse(result.success)


class TestMockLLMAdapter(unittest.TestCase):
    def test_arithmetic_detection(self):
        llm = MockLLMAdapter()
        result = asyncio.run(llm.complete("ROLE: test\nUSER_TASK: 123 乘以 456 等于多少？\n"))
        # Native tool calling: tool calls are in LLMResponse.tool_calls
        self.assertEqual(len(result.tool_calls), 1)
        self.assertEqual(result.tool_calls[0].name, "calculate")
        self.assertIn("123*456", result.tool_calls[0].arguments["expression"])

    def test_tool_result_response(self):
        llm = MockLLMAdapter()
        result = asyncio.run(
            llm.complete(
                "USER_TASK: 123 乘以 456\nCONTEXT:\n(无历史上下文)\n",
                history=[
                    {"role": "assistant", "tool_calls": [{"id": "c1", "name": "calculate"}]},
                    {"role": "tool", "tool_call_id": "c1", "content": "56088"},
                ],
            )
        )
        self.assertIn("56088", result.text)
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


class TestEndToEnd(unittest.TestCase):
    def test_single_agent_qa(self):
        from lca.application.api import Agent
        from lca.infrastructure.llm_adapter.mock_llm import MockLLMAdapter

        agent = Agent(
            role="测试助手",
            goal="回答问题",
            backstory="测试用",
            tools=build_calculator_tools(),
            llm=MockLLMAdapter(),
        )
        result = asyncio.run(agent.run("123 乘以 456 等于多少？"))
        self.assertEqual(result.status, "completed")
        self.assertIsNotNone(result.output)
        self.assertIn("56088", result.output)


if __name__ == "__main__":
    unittest.main()
