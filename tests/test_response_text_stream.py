"""Tests for incremental response_text streaming (LobeHub content contract)."""

from __future__ import annotations

import unittest

from lca.layer0_infra.observability.response_text_stream import (
    ResponseTextStreamExtractor,
    extract_user_facing_answer,
)


class TestExtractUserFacingAnswer(unittest.TestCase):
    def test_plain_prose_passthrough(self) -> None:
        self.assertEqual(extract_user_facing_answer("你好"), "你好")

    def test_respond_json_extracts_response_text(self) -> None:
        raw = '{"action_type": "respond", "response_text": "你好\\n世界"}'
        self.assertEqual(extract_user_facing_answer(raw), "你好\n世界")

    def test_use_tool_json_returns_none(self) -> None:
        raw = '{"action_type": "use_tool", "tool_name": "execute_code"}'
        self.assertIsNone(extract_user_facing_answer(raw))


class TestResponseTextStreamExtractor(unittest.TestCase):
    def test_streams_only_response_text_not_json_keys(self) -> None:
        extractor = ResponseTextStreamExtractor()
        chunks = [
            '{"action_type": "respond", "rationale": "因为", ',
            '"confidence": 0.9, "response_text": "你',
            '好\\n\\n## 标题"}',
        ]
        visible = "".join(extractor.feed(part) for part in chunks)
        self.assertEqual(visible, "你好\n\n## 标题")
        self.assertNotIn("rationale", visible)
        self.assertNotIn("confidence", visible)
        self.assertNotIn("action_type", visible)

    def test_plain_text_stream_passthrough(self) -> None:
        extractor = ResponseTextStreamExtractor()
        self.assertEqual(extractor.feed("你"), "你")
        self.assertEqual(extractor.feed("好"), "好")

    def test_use_tool_emits_nothing_until_response_key(self) -> None:
        extractor = ResponseTextStreamExtractor()
        self.assertEqual(
            extractor.feed('{"action_type": "use_tool", "tool_name": "x"}'),
            "",
        )

    def test_incremental_does_not_repeat(self) -> None:
        extractor = ResponseTextStreamExtractor()
        first = extractor.feed('{"response_text": "ab')
        second = extractor.feed('c"}')
        self.assertEqual(first, "ab")
        self.assertEqual(second, "c")

    def test_provider_tool_markup_not_surfaced(self) -> None:
        extractor = ResponseTextStreamExtractor()
        leaked = "call_call888\n</think>\n<call><call_name>web_search</call_name></call>"
        self.assertEqual(extractor.feed(leaked), "")

    def test_bracket_tool_call_markup_not_surfaced(self) -> None:
        extractor = ResponseTextStreamExtractor()
        leaked = '[Tool call: run_command]\n{"command":"ls"}'
        self.assertEqual(extractor.feed(leaked), "")


if __name__ == "__main__":
    unittest.main()
