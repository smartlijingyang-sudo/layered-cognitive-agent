"""Tests for streaming monologue interception and bubble delivery (ADR-0248 §3.3 / s02, s05)."""

import pytest

from lca.contracts.models.core.state.state import AgentState
from lca.contracts.models.core.state.terminal_outcome import (
    TerminalOutcome,
    TerminalOutcomeKind,
    TextRef,
)
from lca.infrastructure.runtime_plane.capability_bindings import (
    BindingsViewBuilder,
    reset_capability_bindings,
    set_capability_bindings,
)
from lca.infrastructure.vocal.gate import GatedVocalGate
from lca.infrastructure.vocal.tool_adapter import SendMessageVocalTool
from lca.plugins.events.publishers._session_publish import (
    reset_publish_session,
    set_publish_session,
)
from lca.runtime.projection.result_projection import TerminalResultProjection
from lca.session.append import Session


def test_gated_gate_scratchpad_interception():
    gate = GatedVocalGate(operation_id="op_test_intercept")
    gate.handle_text_chunk("Internal reflection chunk 1: evaluating files.\n")
    gate.handle_text_chunk("Internal reflection chunk 2: decided to use box.\n")

    assert len(gate.get_visible_outputs()) == 0
    assert "Internal reflection chunk 1" in gate.get_scratchpad()
    assert "Internal reflection chunk 2" in gate.get_scratchpad()


@pytest.mark.asyncio
async def test_send_message_delivers_and_appends_to_session():
    session = Session("sess_vocal_delivery")
    set_publish_session(session)
    gate = GatedVocalGate(operation_id="op_delivery")

    token = set_capability_bindings(BindingsViewBuilder(vocal_mode="gated", vocal_gate=gate))

    try:
        tool = SendMessageVocalTool(gate)
        obs = await tool.execute({"type": "text", "content": "任务已顺利完成，请查验。"})
        assert obs.success is True
        assert obs.payload["content"] == "任务已顺利完成，请查验。"
        assert obs.payload["status"] == "delivered"

        # 断言 gate 中留存了该正式气泡
        assert len(gate.get_visible_outputs()) == 1
        assert gate.get_visible_outputs()[0]["content"] == "任务已顺利完成，请查验。"

        # 断言 Session 记录了 vocal.message.delivered 事实事件
        events = [e for e in session._log if e.type == "vocal.message.delivered"]
        assert len(events) == 1
        assert events[0].data["content"] == "任务已顺利完成，请查验。"
        assert events[0].visibility == "user"
    finally:
        reset_capability_bindings(token)
        reset_publish_session(None)


@pytest.mark.asyncio
async def test_terminal_result_projection_reads_gated_vocal_delivery():
    gate = GatedVocalGate(operation_id="op_proj")
    tool = SendMessageVocalTool(gate)
    await tool.execute({"type": "text", "content": "正式气泡：环境已部署完毕。"})

    token = set_capability_bindings(BindingsViewBuilder(vocal_mode="gated", vocal_gate=gate))

    try:
        projection = TerminalResultProjection(state_store=None)
        from lca.contracts.models.core.state.state import Budget

        state = AgentState(trace_id="tr_1", task="部署环境", budget=Budget())
        terminal_outcome = TerminalOutcome(
            kind=TerminalOutcomeKind.COMPLETED,
            stop_reason="completed",
            plan_ref="plan://test",
            final_output_ref=TextRef(text=""),  # 模型未产出直接文本，而是通过 send_message 发声
        )

        result = await projection._project_terminal_outcome(
            state, terminal_outcome, declarative_outcome=None
        )
        assert result.output == "正式气泡：环境已部署完毕。"
    finally:
        reset_capability_bindings(token)
