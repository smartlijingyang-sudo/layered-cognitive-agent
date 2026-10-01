"""Passthrough housekeeping completions never leak tool-call markup.

`/v1/chat/completions` housekeeping path has no agent loop, so a model-written
`call`/`<fsWrite>` block is unexecuted by construction. The response must carry
prose plus a server-side no-tool declaration, never the raw markup.
"""

from __future__ import annotations

import unittest

from lca.plugins.transport.webserver.handlers.openai.housekeeping import (
    sanitize_passthrough_text,
)


class TestSanitizePassthroughText(unittest.TestCase):
    def test_plain_prose_passes_through_verbatim(self) -> None:
        text = "Q3 销售总结"
        self.assertEqual(sanitize_passthrough_text(text), text)

    def test_wire_call_markup_is_stripped_with_declaration(self) -> None:
        text = (
            "我来帮你完成这个任务。\n\n"
            "call\n"
            '{"name": "write_file", "arguments": {"path": "/tmp/a.txt", "content": "hi"}}'
        )
        out = sanitize_passthrough_text(text)
        self.assertIn("我来帮你完成这个任务。", out)
        self.assertNotIn("call\n", out)
        self.assertNotIn("write_file", out)
        self.assertIn("不执行工具调用", out)
        self.assertIn("未被执行", out)

    def test_fs_write_markup_is_stripped_with_declaration(self) -> None:
        text = (
            "两个文件都已创建完成。\n\n"
            "<fsWrite>\n<path>/tmp/s.txt</path>\n<content>x</content>\n</fsWrite>"
        )
        out = sanitize_passthrough_text(text)
        self.assertNotIn("<fsWrite>", out)
        self.assertNotIn("</fsWrite>", out)
        self.assertIn("不执行工具调用", out)

    def test_markup_only_response_becomes_declaration(self) -> None:
        out = sanitize_passthrough_text(
            'call\n{"name": "write_file", "arguments": {"path": "/tmp/a.txt"}}'
        )
        self.assertNotIn("call", out)
        self.assertIn("不执行工具调用", out)
