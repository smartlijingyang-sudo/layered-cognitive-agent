"""Partial JSON tool-call arguments become started plugin_state."""

from __future__ import annotations

import unittest

from lca.cognition.brain.tool_call_stream import (
    parse_partial_tool_args,
    push_tool_call_stream,
)


class TestParsePartialToolArgs(unittest.TestCase):
    def test_complete_json(self) -> None:
        args = parse_partial_tool_args('{"code": "print(1)", "language": "python"}')
        self.assertEqual(args["code"], "print(1)")
        self.assertEqual(args["language"], "python")

    def test_partial_code_string(self) -> None:
        args = parse_partial_tool_args('{"code": "import matplotlib\\nprint("')
        self.assertTrue(args["code"].startswith("import matplotlib"))

    def test_write_file_keeps_path_and_partial_content(self) -> None:
        args = parse_partial_tool_args(
            '{"path": "/home/sandbox-user/outputs/a.html", "content": "<!DOCTYPE html>'
        )
        self.assertEqual(args["path"], "/home/sandbox-user/outputs/a.html")
        self.assertTrue(args["content"].startswith("<!DOCTYPE html>"))


class TestPushToolCallStream(unittest.TestCase):
    def test_first_name_opens_card(self) -> None:
        slots: dict = {}
        frame = push_tool_call_stream(
            slots, tool_name="execute_code", tool_call_id="toolu_1", arguments_delta=""
        )
        self.assertIsNotNone(frame)
        assert frame is not None
        self.assertEqual(frame["tool_name"], "execute_code")
        self.assertEqual(frame["tool_call_id"], "toolu_1")

    def test_same_id_throttles_tiny_deltas(self) -> None:
        slots: dict = {}
        first = push_tool_call_stream(
            slots, tool_name="execute_code", tool_call_id="c1", arguments_delta='{"c'
        )
        second = push_tool_call_stream(
            slots, tool_name=None, tool_call_id="c1", arguments_delta="ode"
        )
        self.assertIsNotNone(first)
        self.assertIsNone(second)
