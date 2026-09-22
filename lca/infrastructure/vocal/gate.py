import time
import uuid
from typing import Any

from lca.contracts.models.vocal.models import (
    DeliveryReceipt,
    SendMessagePayload,
    VocalMessageType,
)
from lca.contracts.models.vocal.wake import WakeContext, WakeSource
from lca.contracts.protocols.vocal.protocol import VocalGateProtocol
from lca.infrastructure.vocal.exceptions import VocalGateAlreadyBlockedError
from lca.infrastructure.vocal.wake import WakeClassifier


class DirectVocalGate(VocalGateProtocol):
    """经典直连声带门控：普通文本直接对外发射气泡，零拦截。"""

    def __init__(self, operation_id: str) -> None:
        self.operation_id = operation_id
        self._visible: list[dict[str, Any]] = []

    def handle_text_chunk(self, chunk: str) -> None:
        self._visible.append({"type": "text", "content": chunk})

    def deliver(self, payload: SendMessagePayload) -> DeliveryReceipt:
        self._visible.append({"type": payload.type.value, "content": payload.content})
        return DeliveryReceipt(
            message_id=str(uuid.uuid4()),
            delivered_at_ms=int(time.time() * 1000),
            vocal_type=payload.type,
            is_terminal_for_turn=False,
        )

    def is_awaiting_widget(self) -> bool:
        return False

    def get_visible_outputs(self) -> list[dict[str, Any]]:
        return list(self._visible)

    def get_scratchpad(self) -> str:
        return ""


class GatedVocalGate(VocalGateProtocol):
    """门控声带硬闸：大模型普通文本内省截流，仅允许经由 SendMessage 工具对外发声。"""

    def __init__(
        self,
        operation_id: str,
        wake_source: str | WakeSource = "user_input",
        wake_context: WakeContext | None = None,
    ) -> None:
        self.operation_id = operation_id
        if wake_context is not None:
            self.wake_context = wake_context
            self.wake_source = wake_context.source.value
        else:
            self.wake_context = WakeClassifier().classify(wake_source)
            self.wake_source = self.wake_context.source.value

        self._scratchpad: list[str] = []
        self._visible: list[dict[str, Any]] = []
        self._awaiting_widget: bool = False
        self.has_acked: bool = False
        self.delivered_count: int = 0

    def handle_text_chunk(self, chunk: str) -> None:
        # INV-VOCAL-01: 普通文本被完全截流进内省 scratchpad，绝不进可见气泡
        self._scratchpad.append(chunk)

    def deliver(self, payload: SendMessagePayload) -> DeliveryReceipt:
        # INV-VOCAL-03: Widget 停等中同轮严禁二次发声
        if self._awaiting_widget:
            raise VocalGateAlreadyBlockedError(
                "当前轮次已发送 Widget 停等中，禁止同轮次二次发送消息。"
            )

        msg_id = str(uuid.uuid4())
        now_ms = int(time.time() * 1000)
        is_terminal = False

        if payload.type == VocalMessageType.WIDGET:
            self._awaiting_widget = True
            is_terminal = True
            self._visible.append(
                {
                    "type": "widget",
                    "message_id": msg_id,
                    "content": payload.content,
                    "options": [opt.model_dump() for opt in (payload.options or [])],
                }
            )
        else:
            visible_record: dict[str, Any] = {
                "type": payload.type.value,
                "message_id": msg_id,
                "content": payload.content,
            }
            if self.wake_context.channel_target:
                visible_record["channel_target"] = self.wake_context.channel_target
            self._visible.append(visible_record)

        self.delivered_count += 1
        self.has_acked = True

        return DeliveryReceipt(
            message_id=msg_id,
            delivered_at_ms=now_ms,
            vocal_type=payload.type,
            is_terminal_for_turn=is_terminal,
            requires_user_action=is_terminal,
        )

    def is_awaiting_widget(self) -> bool:
        return self._awaiting_widget

    def get_visible_outputs(self) -> list[dict[str, Any]]:
        return list(self._visible)

    def get_scratchpad(self) -> str:
        return "".join(self._scratchpad)
