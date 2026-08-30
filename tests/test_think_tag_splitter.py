"""ThinkTagStreamSplitter + extract_reasoning_text unit tests."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from lca.infrastructure.llm_adapter.openai_compat._shared import (
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

    def test_orphan_close_tag_stripped(self) -> None:
        """Orphan </think> without <think> must NOT leak into content.

        This is the root cause of the LCA bug where </think> appeared
        in the user-visible answer (step 8 of the PDF generation run).
        """
        s = ThinkTagStreamSplitter()
        parts = s.feed("根据之前的工作，PDF 已经成功生成。让我确认文件并完成导出。\n")
        parts += s.feed("</think>\n\n")
        parts += s.flush()
        merged: dict[str, str] = {"reasoning": "", "content": ""}
        for kind, text in parts:
            merged[kind] += text
        # </think> must be stripped — content should be clean
        self.assertNotIn("</think>", merged["content"])
        self.assertEqual(merged["reasoning"], "")
        self.assertIn("PDF 已经成功生成", merged["content"])

    def test_orphan_close_tag_only(self) -> None:
        """Just an orphan </think> — should produce empty output."""
        s = ThinkTagStreamSplitter()
        parts = s.feed("</think>") + s.flush()
        content_parts = [t for k, t in parts if k == "content"]
        reasoning_parts = [t for k, t in parts if k == "reasoning"]
        self.assertEqual("".join(content_parts), "")
        self.assertEqual("".join(reasoning_parts), "")

    def test_orphan_close_after_closed_think(self) -> None:
        """Orphan </think> after a completed <think>...
        </think>

         block — also stripped."""
        s = ThinkTagStreamSplitter()
        parts = s.feed("<think>thinking</think>answer")
        parts += s.feed("</think>more")
        parts += s.flush()
        merged: dict[str, str] = {"reasoning": "", "content": ""}
        for kind, text in parts:
            merged[kind] += text
        self.assertEqual(merged["reasoning"], "thinking")
        self.assertNotIn("</think>", merged["content"])
        self.assertIn("answer", merged["content"])
        self.assertIn("more", merged["content"])


if __name__ == "__main__":
    unittest.main()
