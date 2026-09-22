from typing import Any

from lca.contracts.models.vocal.models import (
    DeliveryReceipt,
    SendMessagePayload,
    VocalMessageType,
)
from lca.contracts.models.vocal.wake import WakeContext, WakeSource
from lca.contracts.protocols.vocal.protocol import VocalGateProtocol


class RevivalCoordinator:
    """后台子代理完成复苏协调器：接收子代理上报并唤醒父进程统一开口交付。"""

    def __init__(self, parent_gate: VocalGateProtocol) -> None:
        self._parent_gate = parent_gate

    def handle_subagent_completion(
        self, subagent_outcome: dict[str, Any]
    ) -> tuple[WakeContext, DeliveryReceipt]:
        sub_id = str(subagent_outcome.get("subagent_id", "unknown_subagent"))
        summary = str(subagent_outcome.get("summary", "子代理任务已完成。"))

        wake_ctx = WakeContext(
            source=WakeSource.REVIVAL,
            is_silence_allowed=True,
            subagent_id=sub_id,
        )

        delivery_payload = SendMessagePayload(
            type=VocalMessageType.TEXT,
            content=f"[子代理汇报] {summary}",
        )
        receipt = self._parent_gate.deliver(delivery_payload)
        return wake_ctx, receipt
