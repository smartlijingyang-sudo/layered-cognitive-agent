"""ThinkTagStreamSplitter + extract_reasoning_text unit tests."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from lca.layer0_infra.llm_adapter.openai_compat._shared import (
    ThinkTagStreamSplitter,
    extract_reasoning_text,
)


class TestExtractReasoningText(unittest.TestCase):
    def test_reasoning_content_attr(self) -> None:
        delta = SimpleNamespace(reasoning_content="abc", content=None)
        self.assertEqual(extract_reasoning_text(delta), "abc")

    def test_dict_and_model_extra(self) -> None:
        self.assertEqual(extract_reasoning_text({"reasoning": "x"}), "x")
        delta = SimpleNamespace(model_extra={"thinking": "y"})
        self.assertEqual(extract_reasoning_text(delta), "y")

    def test_empty(self) -> None:
        self.assertEqual(extract_reasoning_text(None), "")
        self.assertEqual(extract_reasoning_text(SimpleNamespace(content="hi")), "")


class TestThinkTagStreamSplitter(unittest.TestCase):
    def test_plain_content(self) -> None:
        s = ThinkTagStreamSplitter()
        parts = s.feed("hello") + s.flush()
        self.assertEqual(parts, [("content", "hello")])

    def test_full_think_block(self) -> None:
        s = ThinkTagStreamSplitter()
        parts = s.feed("<think>plan</think>answer") + s.flush()
        self.assertEqual(parts, [("reasoning", "plan"), ("content", "answer")])

    def test_chunked_tags(self) -> None:
        s = ThinkTagStreamSplitter()
        out: list[tuple[str, str]] = []
        for piece in ("<thi", "nk>a", "b</thi", "nk>c"):
            out.extend(s.feed(piece))
        out.extend(s.flush())
        merged: dict[str, str] = {"reasoning": "", "content": ""}
        for kind, text in out:
            merged[kind] += text
        self.assertEqual(merged["reasoning"], "ab")
        self.assertEqual(merged["content"], "c")


if __name__ == "__main__":
    unittest.main()
