"""Tool-call markup in the text channel is decoded, or reported as undecodable.

The two shapes below are real completions, not invented ones:

- ``run_b695b0b85115`` — the model asked for ``search_skill`` in an
  invoke/parameter block. Nothing decoded it, so the block was delivered to the
  user as the final answer and the tool never ran.
- ``run_c6df7c01ccae`` — the model emitted only the trailing close of such a
  block (15 completion tokens, ``finish_reason=stop``). That fragment became
  ``response_text`` and the run committed ``StopReason.CONTINUE`` as a success.
"""

from __future__ import annotations

import unittest

from lca.cognition.brain.prompt.leaked_tool_call import parse_text_channel
from lca.contracts.models.core.conversation.llm import LLMResponse
from lca.plugins.gate.decision_classifier_provider import DefaultDecisionClassifier

_CLOSE_PARAM = "</" + "parameter>"
_CLOSE_FUNC = "</" + "function>"


class TestParseTextChannel(unittest.TestCase):
    def test_bracket_markup_becomes_a_call(self) -> None:
        text = (
            "现在让我先查看 Word 文档的内容结构，然后创建 PPTX 版本。\n\n"
            "[Tool call: run_command]\n"
            '{"command":"officecli view /mnt/data/a.docx outline --json",'
            '"description":"查看Word文档大纲结构"}'
        )
        channel = parse_text_channel(text)
        self.assertEqual(channel.prose, "现在让我先查看 Word 文档的内容结构，然后创建 PPTX 版本。")
        self.assertEqual(channel.undecodable, "")
        self.assertEqual([c.name for c in channel.calls], ["run_command"])
        self.assertIn("officecli view", channel.calls[0].arguments["command"])

    def test_invoke_markup_becomes_a_call(self) -> None:
        text = (
            "Now let me activate the PDF skill and generate the report.\n"
            "<tool_calls>\n"
            '<invoke name="search_skill">\n'
            '<parameter name="query">pdf report generation' + _CLOSE_PARAM + "\n"
            "</invoke>\n"
            "</tool_calls>"
        )
        channel = parse_text_channel(text)
        self.assertEqual(
            channel.prose, "Now let me activate the PDF skill and generate the report."
        )
        self.assertEqual(channel.undecodable, "")
        self.assertEqual([c.name for c in channel.calls], ["search_skill"])
        self.assertEqual(channel.calls[0].arguments, {"query": "pdf report generation"})

    def test_function_markup_with_a_fenced_json_body_becomes_a_call(self) -> None:
        text = (
            "<function=executeCode>\n"
            "```json\n"
            '{"description": "fonts", "language": "python", "code": "print(1)"}\n'
            "```\n" + _CLOSE_FUNC
        )
        channel = parse_text_channel(text)
        self.assertEqual([c.name for c in channel.calls], ["executeCode"])
        self.assertEqual(channel.calls[0].arguments["language"], "python")
        self.assertEqual(channel.undecodable, "")

    def test_dangling_close_tags_are_undecodable_not_prose(self) -> None:
        channel = parse_text_channel("`\n\n" + _CLOSE_PARAM + "\n" + _CLOSE_FUNC + "\n")
        self.assertEqual(channel.calls, ())
        self.assertNotIn(_CLOSE_FUNC, channel.prose)
        self.assertIn(_CLOSE_PARAM, channel.undecodable)

    def test_plain_answer_untouched(self) -> None:
        channel = parse_text_channel("PDF 已成功生成。")
        self.assertEqual(channel.prose, "PDF 已成功生成。")
        self.assertEqual(channel.calls, ())
        self.assertEqual(channel.undecodable, "")

    def test_quoted_grammar_inside_a_code_fence_stays_prose(self) -> None:
        text = '工具调用格式如下：\n```\n<invoke name="x">\n```\n以上是示例。'
        channel = parse_text_channel(text)
        self.assertEqual(channel.undecodable, "")
        self.assertEqual(channel.calls, ())
        self.assertEqual(channel.prose, text)

    def test_decision_classifier_uses_recovered_call(self) -> None:
        text = '[Tool call: run_command]\n{"command":"officecli --version"}'
        decision = DefaultDecisionClassifier().classify(LLMResponse(text=text))
        self.assertEqual(decision.action_type, "use_tool")
        self.assertEqual(decision.tool_calls[0].tool_name, "run_command")
        self.assertEqual(decision.tool_calls[0].arguments["command"], "officecli --version")

    def test_classifier_does_not_answer_with_undecodable_markup(self) -> None:
        decision = DefaultDecisionClassifier().classify(
            LLMResponse(text="`\n\n" + _CLOSE_PARAM + "\n" + _CLOSE_FUNC)
        )
        self.assertEqual(decision.action_type, "use_tool")
        self.assertIsNone(decision.response_text)
        self.assertEqual(decision.tool_calls[0].wire_status, "incomplete")


if __name__ == "__main__":
    unittest.main()
