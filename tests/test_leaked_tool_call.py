"""Leaked ``[Tool call: name]`` prose is recovered as native tool_calls."""

from __future__ import annotations

import unittest

from lca.contracts.models.core.llm import LLMResponse
from lca.cognition.brain.leaked_tool_call import recover_leaked_tool_calls
from lca.plugins.providers.decision_classifier import DefaultDecisionClassifier


class TestRecoverLeakedToolCall(unittest.TestCase):
    def test_officecli_style_markup_becomes_run_command(self) -> None:
        text = (
            "现在让我先查看 Word 文档的内容结构，然后创建 PPTX 版本。\n\n"
            "[Tool call: run_command]\n"
            '{"command":"officecli view /mnt/data/a.docx outline --json",'
            '"description":"查看Word文档大纲结构"}'
        )
        leftover, calls = recover_leaked_tool_calls(text)
        self.assertEqual(leftover, "现在让我先查看 Word 文档的内容结构，然后创建 PPTX 版本。")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].name, "run_command")
        self.assertIn("officecli view", calls[0].arguments["command"])

    def test_plain_answer_untouched(self) -> None:
        leftover, calls = recover_leaked_tool_calls("PDF 已成功生成。")
        self.assertEqual(leftover, "PDF 已成功生成。")
        self.assertEqual(calls, [])

    def test_decision_classifier_uses_recovered_call(self) -> None:
        text = '[Tool call: run_command]\n{"command":"officecli --version"}'
        decision = DefaultDecisionClassifier().classify(LLMResponse(text=text))
        self.assertEqual(decision.action_type, "use_tool")
        self.assertEqual(decision.tool_calls[0].tool_name, "run_command")
        self.assertEqual(decision.tool_calls[0].arguments["command"], "officecli --version")
