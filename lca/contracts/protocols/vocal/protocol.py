from typing import Protocol, runtime_checkable

from lca.contracts.models.vocal.models import (
    DeliveryReceipt,
    SendMessagePayload,
    VocalMode,
    WidgetApproval,
)
from lca.contracts.models.vocal.wake import WakeContext


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

    def reset_awaiting_widget(self) -> None:
        """重置 Widget 停等标记（在用户回复 resume 后调用）。"""
        ...

    def pending_widget_approval(self) -> WidgetApproval | None:
        """返回当前正等待用户审批的 Widget，无则返回 None。

        门控拥有可见消息的形状知识；调用方不得再嗅探
        ``get_visible_outputs`` 的 dict 结构。
        """
        ...

    def delivered_visible_texts(self) -> tuple[str, ...]:
        """返回已正式投递的可见气泡文本（按投递顺序）。

        供终态投影在 ``final_output_ref`` 为空时回退取文本；同样替代
        对 ``get_visible_outputs`` 的 hasattr 嗅探。
        """
        ...


@runtime_checkable
class VocalStrategy(Protocol):
    """声带分发策略，支持 Direct（经典直通）与 Gated（门控硬闸）双模。"""

    @property
    def mode(self) -> VocalMode:
        """策略对应模式。"""
        ...

    def create_gate(
        self,
        operation_id: str,
        wake_source: str = "user_input",
        wake_context: WakeContext | None = None,
    ) -> VocalGateProtocol:
        """为特定 Run 创建专用声带门控实例。"""
        ...
