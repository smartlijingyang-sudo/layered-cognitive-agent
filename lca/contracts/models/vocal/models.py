from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class VocalMode(StrEnum):
    """声带分发模式。"""

    DIRECT = "direct"
    GATED = "gated"


class VocalMessageType(StrEnum):
    """声带消息投递类型。"""

    TEXT = "text"
    ATTACHMENT = "attachment"
    WIDGET = "widget"
    SECRET_REQUEST = "secret_request"  # noqa: S105  # enum 名,非密码


class WidgetOption(BaseModel):
    """结构化选项卡中的单项选项。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(..., description="选项唯一标识")
    label: str = Field(..., description="选项按钮展示文字")
    description: str | None = Field(default=None, description="选项详细说明")
    variant: Literal["default", "primary", "danger"] = Field(
        default="default", description="按钮视觉样式"
    )


class SendMessagePayload(BaseModel):
    """通过 send_message 声带向用户投递的强类型载荷。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    type: VocalMessageType = Field(default=VocalMessageType.TEXT, description="投递类型")
    content: str | None = Field(default=None, description="正式文本气泡内容")
    options: list[WidgetOption] | None = Field(
        default=None, description="交互选项列表（1-6项，widget必填）"
    )
    secret_key: str | None = Field(default=None, description="凭证标识键名（secret_request必填）")
    reply_to_id: str | None = Field(default=None, description="关联的上下文消息ID")

    @model_validator(mode="after")
    def validate_payload_semantics(self) -> "SendMessagePayload":
        if self.type == VocalMessageType.TEXT and not self.content:
            raise ValueError("type='text' 时 content 字段不能为空")
        if self.type == VocalMessageType.WIDGET and (
            not self.options or len(self.options) < 1 or len(self.options) > 6
        ):
            raise ValueError("type='widget' 时 options 必须包含 1 到 6 个选项")
        if self.type == VocalMessageType.SECRET_REQUEST and not self.secret_key:
            raise ValueError("type='secret_request' 时 secret_key 字段不能为空")
        return self


class DeliveryReceipt(BaseModel):
    """消息投递不可变执行回执。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    message_id: str
    delivered_at_ms: int
    vocal_type: VocalMessageType
    is_terminal_for_turn: bool = False
    requires_user_action: bool = False
