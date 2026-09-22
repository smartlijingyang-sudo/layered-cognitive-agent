from typing import Protocol, runtime_checkable

from lca.contracts.models.vocal.models import (
    DeliveryReceipt,
    SendMessagePayload,
    VocalMode,
)


@runtime_checkable
class VocalGateProtocol(Protocol):
    """声带门控协议，定义文本内省流拦截与正式投递接口。"""

    def handle_text_chunk(self, chunk: str) -> None:
        """处理模型常规输出 Token / 文本。"""
        ...

    def deliver(self, payload: SendMessagePayload) -> DeliveryReceipt:
        """正式向对外可见声带投递消息。"""
        ...

    def is_awaiting_widget(self) -> bool:
        """当前轮次是否正等待 Widget 用户选择。"""
        ...


@runtime_checkable
class VocalStrategy(Protocol):
    """声带分发策略，支持 Direct（经典直通）与 Gated（门控硬闸）双模。"""

    @property
    def mode(self) -> VocalMode:
        """策略对应模式。"""
        ...

    def create_gate(self, operation_id: str, wake_source: str = "user_input") -> VocalGateProtocol:
        """为特定 Run 创建专用声带门控实例。"""
        ...
