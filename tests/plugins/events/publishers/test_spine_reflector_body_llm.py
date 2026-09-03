"""spine_reflector_body_llm publisher 端到端测试（ADR-0181 PR-3）。

旧 body_llm reflector 全部 9 emit（tool.execute.start/end + retry +
sandbox.enter/exit + decision.start/end + llm.call.start/end +
stream.token + stream.stall）在 EventBus 路径下能正常 publish + 鉴权通过。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from lca_kernel.events.bus import EventBus
from lca_kernel.events.registry import EventRegistry


@pytest.fixture
def bus() -> EventBus:
    """用工作区 lca_kernel/events/config 构造机制。"""
    config_dir = Path(__file__).resolve().parents[4] / "lca_kernel" / "events" / "config"
    return EventBus(EventRegistry.load(config_dir))


def _run(bus: EventBus) -> None:
    from lca.plugins.events.publishers.spine_reflector_body_llm import (
        plugin,
    )

    EventBus.set_default(bus)
    try:
        # tool execute
        ref = plugin.emit_body_tool_execute_start(
            tool_name="search", invocation_id="inv-1", attempt=1
        )
        assert ref.category == "spine.body.tool.execute.start"
        ref = plugin.emit_body_tool_execute_end(
            tool_name="search", invocation_id="inv-1", attempt=1, outcome="success"
        )
        assert ref.category == "spine.body.tool.execute.end"
        # retry
        ref = plugin.emit_body_tool_retry(
            tool_name="search", invocation_id="inv-1", attempt=2, reason="timeout"
        )
        assert ref.category == "spine.body.tool.retry"
        # sandbox
        ref = plugin.emit_body_sandbox_enter(invocation_id="inv-1", tool_name="search")
        assert ref.category == "spine.body.sandbox.enter"
        ref = plugin.emit_body_sandbox_exit(invocation_id="inv-1", tool_name="search")
        assert ref.category == "spine.body.sandbox.exit"
        # decision wrapper
        ref = plugin.emit_body_tool_decision_start(
            tool_name="search", invocation_id="inv-1"
        )
        assert ref.category == "spine.body.tool.execute.start"
        ref = plugin.emit_body_tool_decision_end(
            tool_name="search", invocation_id="inv-1", outcome="success"
        )
        assert ref.category == "spine.body.tool.execute.end"
        # llm
        ref = plugin.emit_llm_call_start(model="gpt-4", stream=False, prompt_preview="hi")
        assert ref.category == "spine.llm.call.start"
        ref = plugin.emit_llm_call_end(model="gpt-4", stream=False, outcome="success")
        assert ref.category == "spine.llm.call.end"
        ref = plugin.emit_llm_stream_token(
            model="gpt-4", text_delta="hello", seq=1, channel_kind="output"
        )
        assert ref.category == "spine.llm.stream.token"
        ref = plugin.emit_llm_stream_stall(model="gpt-4", idle_ms=500, seq=1)
        assert ref.category == "spine.llm.stream.stall"
    finally:
        EventBus.set_default(None)


def test_emit_body_llm_all(bus: EventBus) -> None:
    _run(bus)


def test_unauthorized_publisher_rejected(bus: EventBus) -> None:
    from lca_kernel.events.errors import UnauthorizedPublishError
    from lca_kernel.events.payloads import SpineEventPayload

    class NotInWhitelist:
        pass

    with pytest.raises(UnauthorizedPublishError):
        bus.publish(
            SpineEventPayload(
                execution_point="body.tool.execute.start",
                channel="control",
                payload={"tool_name": "t", "invocation_id": "i", "attempt": 1},
            ),
            producer=NotInWhitelist,
        )
