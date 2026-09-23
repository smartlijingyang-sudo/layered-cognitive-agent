"""Tests for SendMessageVocalTool — ADR-0248 Tool 协议适配器。

验证适配器满足 ``lca.contracts.protocols.Tool`` 协议（name/parameters/
is_idempotent/default_timeout_s/validate/execute → Observation），
并通过门控声带真正投递气泡。
"""

from __future__ import annotations

import asyncio

from lca.infrastructure.vocal.gate import GatedVocalGate
from lca.infrastructure.vocal.tool_adapter import SendMessageVocalTool


def _run(coro):
    return asyncio.run(coro)


def test_satisfies_tool_protocol_surface() -> None:
    gate = GatedVocalGate("op_1")
    tool = SendMessageVocalTool(gate)
    assert tool.name == "send_message"
    assert tool.description
    assert tool.parameters["type"] == "object"
    assert tool.is_idempotent is True
    assert tool.default_timeout_s > 0


def test_delivers_text_observation() -> None:
    gate = GatedVocalGate("op_2")
    tool = SendMessageVocalTool(gate)
    obs = _run(tool.execute({"type": "text", "content": "正在为你排查..."}))
    assert obs.success is True
    assert obs.payload["status"] == "delivered"
    visible = gate.get_visible_outputs()
    assert len(visible) == 1
    assert visible[0]["content"] == "正在为你排查..."
    assert gate.has_acked is True


def test_validate_requires_content_for_text() -> None:
    gate = GatedVocalGate("op_3")
    tool = SendMessageVocalTool(gate)
    err = tool.validate({"type": "text"})
    assert err is not None
    assert "content" in err
    assert tool.validate({"type": "text", "content": "ok"}) is None


def test_plain_text_never_visible_without_send_message() -> None:
    gate = GatedVocalGate("op_4")
    gate.handle_text_chunk("Internal scratchpad introspection")
    assert len(gate.get_visible_outputs()) == 0
