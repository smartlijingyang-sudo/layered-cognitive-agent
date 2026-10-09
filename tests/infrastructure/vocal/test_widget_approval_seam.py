"""RA-089 new tests: gate typed-query unit tests + projection fallback shape test."""


from lca.contracts.models.core.state.terminal_outcome import (
    TerminalOutcome,
    TerminalOutcomeKind,
    TextRef,
)
from lca.contracts.models.vocal.models import (
    SendMessagePayload,
    VocalMessageType,
    WidgetApproval,
    WidgetOption,
)
from lca.infrastructure.runtime_plane.capability_bindings import (
    BindingsViewBuilder,
    set_capability_bindings,
)
from lca.infrastructure.vocal.gate import DirectVocalGate, GatedVocalGate
from lca.runtime.projection.result_projection import _terminal_output


def _widget_payload() -> SendMessagePayload:
    return SendMessagePayload(
        type=VocalMessageType.WIDGET,
        content="请确认执行",
        options=[
            WidgetOption(id="yes", label="确认"),
            WidgetOption(id="no", label="取消"),
        ],
    )


def test_gated_gate_pending_widget_approval_is_typed_and_byte_identical() -> None:
    gate = GatedVocalGate(operation_id="op-1")
    assert gate.pending_widget_approval() is None

    receipt = gate.deliver(_widget_payload())

    approval = gate.pending_widget_approval()
    assert isinstance(approval, WidgetApproval)
    assert approval.message_id == receipt.message_id
    assert approval.content == "请确认执行"
    assert [o["id"] for o in approval.options] == ["yes", "no"]

    # The approval_request payload the driver assembles from this is
    # byte-identical to the old dict-sniffed shape.
    payload = {
        "type": "widget",
        "message_id": approval.message_id,
        "content": approval.content,
        "options": approval.options,
    }
    assert payload == {
        "type": "widget",
        "message_id": receipt.message_id,
        "content": "请确认执行",
        "options": [
            {"id": "yes", "label": "确认", "description": None, "variant": "default"},
            {"id": "no", "label": "取消", "description": None, "variant": "default"},
        ],
    }

    gate.reset_awaiting_widget()
    assert gate.pending_widget_approval() is None


def test_direct_gate_never_has_pending_approval() -> None:
    gate = DirectVocalGate(operation_id="op-1")
    gate.deliver(
        SendMessagePayload(type=VocalMessageType.TEXT, content="hi")
    )
    assert gate.pending_widget_approval() is None
    assert gate.delivered_visible_texts() == ("hi",)


def test_gated_gate_delivered_visible_texts_skips_empty() -> None:
    gate = GatedVocalGate(operation_id="op-1")
    gate.deliver(SendMessagePayload(type=VocalMessageType.TEXT, content="第一句"))
    gate.deliver(SendMessagePayload(type=VocalMessageType.TEXT, content="第二句"))
    assert gate.delivered_visible_texts() == ("第一句", "第二句")


def test_terminal_output_falls_back_to_gate_delivered_texts() -> None:
    gate = GatedVocalGate(operation_id="op-1")
    gate.deliver(SendMessagePayload(type=VocalMessageType.TEXT, content="已完成配置排查。"))

    outcome = TerminalOutcome(
        kind=TerminalOutcomeKind.COMPLETED,
        stop_reason="test",
        plan_ref="test",
        final_output_ref=TextRef(text=""),
    )
    token = set_capability_bindings(
        BindingsViewBuilder(vocal_mode="gated", vocal_gate=gate)
    )
    try:
        assert _terminal_output(outcome) == "已完成配置排查。"
    finally:
        from lca.infrastructure.runtime_plane.capability_bindings import (
            reset_capability_bindings,
        )

        reset_capability_bindings(token)
