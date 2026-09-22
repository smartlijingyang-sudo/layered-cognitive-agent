from typing import Any

from lca.contracts.models.vocal.models import (
    SendMessagePayload,
    VocalMessageType,
    WidgetOption,
)
from lca.contracts.protocols.vocal.protocol import VocalGateProtocol


class SendMessageTool:
    """向用户对外唯一声道发射正式消息的原语工具。

    在门控模式下，大模型普通内省文本用户不可见，必须调用此工具交付气泡或选项卡。
    支持类型：text（普通气泡）、widget（选项卡停等）、secret_request（敏感凭证输入）。
    """

    name: str = "send_message"
    description: str = (
        "向用户对外唯一声道发射正式消息。在门控模式下，大模型普通内省文本用户不可见，"
        "必须调用此工具交付气泡或选项卡。支持类型：text（普通气泡）、widget（选项卡停等）、secret_request（敏感凭证输入）。"
    )

    def __init__(self, gate: VocalGateProtocol) -> None:
        self._gate = gate

    def execute(
        self,
        type: str = "text",
        content: str | None = None,
        options: list[dict[str, Any]] | None = None,
        secret_key: str | None = None,
        reply_to_id: str | None = None,
    ) -> dict[str, Any]:
        parsed_options = [WidgetOption(**opt) for opt in options] if options else None
        payload = SendMessagePayload(
            type=VocalMessageType(type),
            content=content,
            options=parsed_options,
            secret_key=secret_key,
            reply_to_id=reply_to_id,
        )
        receipt = self._gate.deliver(payload)
        return {
            "status": "delivered",
            "message_id": receipt.message_id,
            "vocal_type": receipt.vocal_type.value,
            "is_terminal_for_turn": receipt.is_terminal_for_turn,
            "requires_user_action": receipt.requires_user_action,
        }
