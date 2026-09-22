import pytest
from pydantic import ValidationError

from lca.contracts.models.vocal.models import (
    DeliveryReceipt,
    SendMessagePayload,
    VocalMessageType,
    VocalMode,
    WidgetOption,
)


def test_vocal_mode_and_message_type_enums():
    assert VocalMode.DIRECT == "direct"
    assert VocalMode.GATED == "gated"
    assert VocalMessageType.TEXT == "text"
    assert VocalMessageType.WIDGET == "widget"
    assert VocalMessageType.ATTACHMENT == "attachment"
    assert VocalMessageType.SECRET_REQUEST == "secret_request"


def test_send_message_payload_text_validation():
    payload = SendMessagePayload(type=VocalMessageType.TEXT, content="Hello User")
    assert payload.content == "Hello User"
    assert payload.type == VocalMessageType.TEXT

    with pytest.raises(ValueError, match="content 字段不能为空"):
        SendMessagePayload(type=VocalMessageType.TEXT, content=None)


def test_send_message_payload_widget_validation():
    opt = WidgetOption(id="opt1", label="Option 1", variant="primary")
    payload = SendMessagePayload(type=VocalMessageType.WIDGET, options=[opt])
    assert len(payload.options) == 1

    # Empty options should fail
    with pytest.raises(ValueError, match="options 必须包含 1 到 6 个选项"):
        SendMessagePayload(type=VocalMessageType.WIDGET, options=[])

    # > 6 options should fail
    lots_opts = [WidgetOption(id=f"o{i}", label=f"L{i}") for i in range(7)]
    with pytest.raises(ValueError, match="options 必须包含 1 到 6 个选项"):
        SendMessagePayload(type=VocalMessageType.WIDGET, options=lots_opts)


def test_send_message_payload_secret_request_validation():
    payload = SendMessagePayload(type=VocalMessageType.SECRET_REQUEST, secret_key="GITHUB_TOKEN")
    assert payload.secret_key == "GITHUB_TOKEN"

    with pytest.raises(ValueError, match="secret_key 字段不能为空"):
        SendMessagePayload(type=VocalMessageType.SECRET_REQUEST, secret_key=None)


def test_models_are_frozen():
    opt = WidgetOption(id="opt1", label="Option 1")
    with pytest.raises(ValidationError):
        opt.label = "Changed"  # type: ignore


def test_delivery_receipt_model():
    receipt = DeliveryReceipt(
        message_id="msg_123",
        delivered_at_ms=1700000000,
        vocal_type=VocalMessageType.TEXT,
        is_terminal_for_turn=False,
    )
    assert receipt.message_id == "msg_123"
    assert receipt.vocal_type == VocalMessageType.TEXT
    assert receipt.is_terminal_for_turn is False
    assert receipt.requires_user_action is False
