"""MockLLM 流式输出 rationale 作为 REASONING_TEXT_DELTA。"""

from __future__ import annotations

import json
import unittest

from lca.contracts.atoms.enums import LLMStreamEventType
from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter


class TestMockLLMReasoningStream(unittest.IsolatedAsyncioTestCase):
    async def test_stream_emits_rationale_as_reasoning_then_json(self) -> None:
        adapter = MockLLMAdapter()
        events = [e async for e in adapter.stream("USER_TASK: 你好\n")]
        reasoning = [e for e in events if e.type == LLMStreamEventType.REASONING_TEXT_DELTA]
        content = [e for e in events if e.type == LLMStreamEventType.OUTPUT_TEXT_DELTA]
        completed = [e for e in events if e.type == LLMStreamEventType.COMPLETED]
        self.assertTrue(reasoning)
        self.assertTrue(content)
        self.assertEqual(len(completed), 1)
        rationale = "".join(e.text for e in reasoning)
        body = "".join(e.text for e in content)
        payload = json.loads(body)
        self.assertIn("rationale", payload)
        self.assertEqual(rationale, payload["rationale"])


if __name__ == "__main__":
    unittest.main()
