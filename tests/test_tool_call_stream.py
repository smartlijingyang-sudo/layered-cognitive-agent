"""Partial JSON tool-call arguments parser + stream accumulator.

本批 (fix/strip-tool-call-streaming) 改造后,executor 不再为每 delta emit
journal 事件,但 ``parse_partial_tool_args`` 与 ``push_tool_call_stream``
仍存在 —— 前者是 hint 通道(若前端订阅)所需,后者是 slot 累积核心。
ToolCallResolved 直接对完整 raw 调 ``parse_completed_slot_args`` (新),
``parse_partial_tool_args`` 仅供 partial preview 场景。
"""

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

    def test_same_id_emits_per_growing_chunk(self) -> None:
        """ADR-0101 followup (2026-09-01): emit on every chunk that grows raw.

        旧逻辑按 160 字符节流,小 payload (e.g. ``{"code": "print(2)"}`` ~20 chars)
        永远走不到阈值,LobeHub 拿不到任何 preview。新逻辑:每次 raw 增长就 emit。
        """
        slots: dict = {}
        first = push_tool_call_stream(
            slots, tool_name="execute_code", tool_call_id="c1", arguments_delta='{"c'
        )
        second = push_tool_call_stream(
            slots, tool_name=None, tool_call_id="c1", arguments_delta="ode"
        )
        self.assertIsNotNone(first)
        # 新行为:raw 增长了就 emit (5 chars → 8 chars)
        self.assertIsNotNone(second)
        # 但 raw 不变就不 emit (de-dup)
        third = push_tool_call_stream(slots, tool_name=None, tool_call_id="c1", arguments_delta="")
        self.assertIsNone(third)

    def test_slot_raw_accumulates_deltas(self) -> None:
        """slot['raw'] 累积所有 delta,供 executor 在 COMPLETED 前
        emit ToolCallResolved 时取完整 args。"""
        slots: dict = {}
        # 第一次 emit 触发
        first = push_tool_call_stream(
            slots,
            tool_name="executeCode",
            tool_call_id="c2",
            arguments_delta='{"code": "import os',
        )
        assert first is not None
        # 累积 delta (不触发 emit 因为 < 160 字符)
        push_tool_call_stream(
            slots,
            tool_name=None,
            tool_call_id="c2",
            arguments_delta="\ncode = '''#!/usr/bin/env python3",
        )
        # slot["raw"] 必须累积
        assert slots["c2"]["raw"].startswith('{"code": "import os')
        assert "python3" in slots["c2"]["raw"]
        # 第三次凑够 160 字符阈值 → 第二次 emit
        # 补足到至少 160 字符
        more = "x" * (200 - len(slots["c2"]["raw"]))
        third = push_tool_call_stream(
            slots,
            tool_name=None,
            tool_call_id="c2",
            arguments_delta=more,
        )
        # third 应触发 emit (返回非 None)
        assert third is not None
        assert len(slots["c2"]["raw"]) >= 160

        # raw 可以被 parse_partial_tool_args 还原 partial dict
        from lca.cognition.brain.tool_call_stream import parse_partial_tool_args

        partial = parse_partial_tool_args(slots["c2"]["raw"])
        assert isinstance(partial, dict)
