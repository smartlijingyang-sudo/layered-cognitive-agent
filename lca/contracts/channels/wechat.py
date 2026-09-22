"""DTO contracts for WeChat channel integration."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class WechatQrResult(BaseModel):
    """Result of requesting a WeChat iLink bot QR code."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    qrcode: str
    qrcode_img_content: str


class WechatStatusResult(BaseModel):
    """Result of polling a WeChat iLink bot QR code status."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["wait", "scaned", "confirmed", "expired"]
    bot_token: str | None = None
    ilink_bot_id: str | None = None
    ilink_user_id: str | None = None
    baseurl: str | None = None


class WechatChannelConfig(BaseModel):
    """Persisted configuration for an Assistant's WeChat channel."""

    model_config = ConfigDict(extra="forbid")

    bot_id: str
    bot_token: str
    user_id: str
    base_url: str = "https://ilinkai.weixin.qq.com"
    enabled: bool = True
    display_tool_calls: bool = False
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
