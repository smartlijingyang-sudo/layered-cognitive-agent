import pytest

from lca.infrastructure.vocal.exceptions import VocalGateAlreadyBlockedError
from lca.infrastructure.vocal.gate import GatedVocalGate
from lca.infrastructure.vocal.tool import SendMessageTool


def test_send_message_tool_text_delivery():
    gate = GatedVocalGate("op_1")
    tool = SendMessageTool(gate)

    res = tool.execute(type="text", content="Hello via tool")
    assert res["status"] == "delivered"
    assert res["vocal_type"] == "text"
    assert res["is_terminal_for_turn"] is False
    assert len(gate.get_visible_outputs()) == 1
    assert gate.get_visible_outputs()[0]["content"] == "Hello via tool"


def test_send_message_tool_widget_blocks_further_sends():
    gate = GatedVocalGate("op_2")
    tool = SendMessageTool(gate)

    options = [{"id": "y", "label": "Yes"}, {"id": "n", "label": "No"}]
    res = tool.execute(type="widget", content="Are you sure?", options=options)
    assert res["is_terminal_for_turn"] is True
    assert gate.is_awaiting_widget() is True

    # INV-VOCAL-03: Widget 投递后同轮次严禁二次发声，必抛 VocalGateAlreadyBlockedError
    with pytest.raises(VocalGateAlreadyBlockedError):
        tool.execute(type="text", content="Should be blocked")
