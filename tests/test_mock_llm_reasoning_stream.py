"""MockLLM 流式输出验证。"""

from __future__ import annotations

import unittest

from lca.contracts.atoms.enums import LLMStreamEventType
from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter


class TestMockLLMReasoningStream(unittest.IsolatedAsyncioTestCase):
    async def test_stream_emits_text_response(self) -> None:
        adapter = MockLLMAdapter()
        events = [e async for e in adapter.stream("USER_TASK: 你好\n")]
        content = [e for e in events if e.type == LLMStreamEventType.OUTPUT_TEXT_DELTA]
        completed = [e for e in events if e.type == LLMStreamEventType.COMPLETED]
        self.assertTrue(content)
        self.assertEqual(len(completed), 1)
        body = "".join(e.text for e in content)
        self.assertTrue(body)

    async def test_stream_emits_tool_call_for_arithmetic(self) -> None:
        adapter = MockLLMAdapter()
        events = [e async for e in adapter.stream("USER_TASK: 1 + 2 + 3\n")]
        tool_deltas = [
            e for e in events if e.type == LLMStreamEventType.FUNCTION_CALL_ARGUMENTS_DELTA
        ]
        completed = [e for e in events if e.type == LLMStreamEventType.COMPLETED]
        self.assertTrue(tool_deltas)
        self.assertEqual(len(completed), 1)
        self.assertEqual(tool_deltas[0].tool_name, "calculate")


if __name__ == "__main__":
    unittest.main()
