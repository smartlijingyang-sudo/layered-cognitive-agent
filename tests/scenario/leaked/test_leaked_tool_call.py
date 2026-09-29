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

    def test_tool_tag_with_param_becomes_a_call(self) -> None:
        text = (
            "现在开始协助您。\n"
            '<tool name="delegate_to_role">\n'
            '<param name="target_role">sales</param>\n'
            '<param name="subtask">分析折扣限制</param>\n'
            "</tool>"
        )
        channel = parse_text_channel(text)
        self.assertEqual(channel.prose, "现在开始协助您。")
        self.assertEqual(channel.undecodable, "")
        self.assertEqual([c.name for c in channel.calls], ["delegate_to_role"])
        self.assertEqual(
            channel.calls[0].arguments,
            {"target_role": "sales", "subtask": "分析折扣限制"},
        )

    def test_tool_tag_with_json_body_becomes_a_call(self) -> None:
        text = (
            "我来计算一下总额：\n"
            '<tool name="calculator">{"expression": "400 + 15"}</tool>'
        )
        channel = parse_text_channel(text)
        self.assertEqual(channel.prose, "我来计算一下总额：")
        self.assertEqual(channel.undecodable, "")
        self.assertEqual([c.name for c in channel.calls], ["calculator"])
        self.assertEqual(channel.calls[0].arguments, {"expression": "400 + 15"})

    def test_tool_call_json_block_becomes_a_call(self) -> None:
        text = (
            "查询中：\n"
            "<tool_call>\n"
            '{"name": "fetch_user", "arguments": {"user_id": 123}}\n'
            "</tool_call>"
        )
        channel = parse_text_channel(text)
        self.assertEqual(channel.prose, "查询中：")
        self.assertEqual(channel.undecodable, "")
        self.assertEqual([c.name for c in channel.calls], ["fetch_user"])
        self.assertEqual(channel.calls[0].arguments, {"user_id": 123})

    def test_delegate_to_xml_block_becomes_a_call(self) -> None:
        text = (
            "我需要法务专家介入：\n"
            "<delegate_to>\n"
            "<role>legal</role>\n"
            "<subtask>审核合同条款</subtask>\n"
            "</delegate_to>"
        )
        channel = parse_text_channel(text)
        self.assertEqual(channel.prose, "我需要法务专家介入：")
        self.assertEqual(channel.undecodable, "")
        self.assertEqual([c.name for c in channel.calls], ["delegate"])
        self.assertEqual(
            channel.calls[0].arguments,
            {"target_role": "legal", "subtask": "审核合同条款"},
        )

    def test_qwen_special_token_tool_call_becomes_a_call(self) -> None:
        text = (
            "运行命令：\n"
            "<|tool_calls|><|tool_call_begin|>run_cmd<|tool_call_begin|>"
            '{"cmd": "pytest"}<|tool_call_end|>'
        )
        channel = parse_text_channel(text)
        self.assertEqual(channel.prose, "运行命令：")
        self.assertEqual(channel.undecodable, "")
        self.assertEqual([c.name for c in channel.calls], ["run_cmd"])
        self.assertEqual(channel.calls[0].arguments, {"cmd": "pytest"})

    def test_modern_dangling_tags_become_undecodable(self) -> None:
        channel = parse_text_channel("完成分析。\n</tool>\n</delegate_to>")
        self.assertEqual(channel.calls, ())
        self.assertEqual(channel.prose, "完成分析。")
        self.assertIn("</tool>", channel.undecodable)
        self.assertIn("</delegate_to>", channel.undecodable)


if __name__ == "__main__":
    unittest.main()
