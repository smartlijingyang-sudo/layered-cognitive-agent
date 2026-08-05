"""LCA Framework 单元测试 —— 验证核心契约与端到端流程。"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lca.contracts.state import AgentState, Budget
from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter
from lca.layer0_infra.tools.calculator_tool import CalculatorTool
from lca.layer1_cognitive.brain.decision_parser import SimpleDecisionParser


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
        tool = CalculatorTool()
        result = asyncio.run(tool.execute({"expression": "2 + 3 * 4"}))
        self.assertTrue(result.success)
        self.assertEqual(result.payload, 14)

    def test_invalid_expression(self):
        tool = CalculatorTool()
        result = asyncio.run(tool.execute({"expression": "import os"}))
        self.assertFalse(result.success)


class TestMockLLMAdapter(unittest.TestCase):
    def test_arithmetic_detection(self):
        llm = MockLLMAdapter()
        result = asyncio.run(llm.complete("ROLE: test\nUSER_TASK: 123 乘以 456 等于多少？\n"))
        self.assertIn("use_tool", result.text)
        self.assertIn("calculator", result.text)

    def test_tool_result_response(self):
        llm = MockLLMAdapter()
        result = asyncio.run(
            llm.complete("USER_TASK: 123 乘以 456\nCONTEXT:\nTOOL_RESULT: 56088\n")
        )
        self.assertIn("respond", result.text)
        self.assertIn("56088", result.text)


class TestDecisionParser(unittest.TestCase):
    def test_parse_tool_call(self):
        parser = SimpleDecisionParser()
        state = AgentState(trace_id="t", task="test", budget=Budget())
        raw = '{"action_type": "use_tool", "tool_name": "calculator", "arguments": {"expression": "1+1"}, "rationale": "calc", "confidence": 0.9}'
        decision = parser.parse(raw, state)
        self.assertEqual(decision.action_type, "use_tool")
        self.assertEqual(len(decision.tool_calls), 1)
        self.assertEqual(decision.tool_calls[0].tool_name, "calculator")

    def test_parse_fallback(self):
        parser = SimpleDecisionParser()
        state = AgentState(trace_id="t", task="test", budget=Budget())
        decision = parser.parse("not json", state)
        self.assertEqual(decision.action_type, "respond")
        self.assertEqual(decision.confidence, 0.1)


class TestEndToEnd(unittest.TestCase):
    def test_single_agent_qa(self):
        from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter
        from lca.layer0_infra.tools.calculator_tool import CalculatorTool
        from lca.layer4_app.api import Agent

        agent = Agent(
            role="测试助手",
            goal="回答问题",
            backstory="测试用",
            tools=[CalculatorTool()],
            llm=MockLLMAdapter(),
        )
        result = asyncio.run(agent.run("123 乘以 456 等于多少？"))
        self.assertEqual(result.status, "completed")
        self.assertIsNotNone(result.output)
        self.assertIn("56088", result.output)


if __name__ == "__main__":
    unittest.main()
