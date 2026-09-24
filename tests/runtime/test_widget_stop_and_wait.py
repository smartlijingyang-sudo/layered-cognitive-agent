"""Tests for widget stop-and-wait state machine and resume flow (ADR-0248 §3.3 / s03).

Invariants tested:
- INV-03: Widget 触发停等状态（WAITING_INPUT），同轮二次发声必定报错阻断，提交 answer 顺畅恢复。
"""

import pytest

from lca.contracts.models.core.execution.decision import ToolCall, requires_human_input
from lca.infrastructure.vocal.exceptions import VocalGateAlreadyBlockedError
from lca.infrastructure.vocal.gate import GatedVocalGate
from lca.infrastructure.vocal.tool import SendMessageTool
from lca.runtime.support.resume_input import HumanAnswerResumeInputAdapter


def test_widget_stops_turn_and_blocks_second_message():
    gate = GatedVocalGate(operation_id="op_w")
    tool = SendMessageTool(gate)

    res = tool.execute(
        type="widget",
        content="请选择部署环境：",
        options=[{"id": "staging", "label": "测试环境"}, {"id": "prod", "label": "生产环境"}],
    )
    assert res["status"] == "delivered"
    assert res["is_terminal_for_turn"] is True
    assert res["requires_user_action"] is True
    assert gate.is_awaiting_widget() is True

    # 同轮严禁二次发声（INV-03）
    with pytest.raises(VocalGateAlreadyBlockedError):
        tool.execute(type="text", content="多余的一句话")


def test_requires_human_input_identifies_widget_call():
    widget_call = ToolCall(
        call_id="call_w1",
        tool_name="send_message",
        arguments={"type": "widget", "options": [{"id": "1", "label": "确认"}]},
    )
    text_call = ToolCall(
        call_id="call_t1",
        tool_name="send_message",
        arguments={"type": "text", "content": "普通文本"},
    )
    other_call = ToolCall(
        call_id="call_o1",
        tool_name="box_run_command",
        arguments={"command": "ls -la"},
    )

    assert requires_human_input([widget_call]) is True
    assert requires_human_input([text_call]) is False
    assert requires_human_input([other_call]) is False


def test_widget_gate_resets_on_resume():
    gate = GatedVocalGate(operation_id="op_resume")
    tool = SendMessageTool(gate)
    tool.execute(
        type="widget",
        content="请确认操作：",
        options=[{"id": "yes", "label": "确认"}],
    )
    assert gate.is_awaiting_widget() is True

    # 模拟用户通过 /answer 恢复
    adapter = HumanAnswerResumeInputAdapter()
    resume_input = adapter.normalize("测试环境")
    assert resume_input.input_value == "测试环境"

    # 重置等待标记后，次轮可正常发声
    gate.reset_awaiting_widget()
    assert gate.is_awaiting_widget() is False

    next_res = tool.execute(type="text", content="收到选择：测试环境，开始部署。")
    assert next_res["status"] == "delivered"
    assert gate.delivered_count == 2
