"""Browser and Desktop domain contract models (ADR-0248 §5.3, §6 / s06, s13)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class BrowserActionType(StrEnum):
    """浏览器子代理动作类型枚举。"""

    NAVIGATE = "navigate"
    CLICK = "click"
    TYPE = "type"
    SCREENSHOT = "screenshot"
    EXTRACT_TEXT = "extract_text"
    CLOSE = "close"


class BrowserAction(BaseModel):
    """浏览器子代理执行动作请求载荷。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    action_type: BrowserActionType = Field(..., description="浏览器操作动作类型")
    url: str | None = Field(default=None, description="导航目标 URL")
    selector: str | None = Field(default=None, description="DOM CSS/XPath 选择器")
    text: str | None = Field(default=None, description="输入文本内容")
    timeout_s: int = Field(default=30, description="单步超时时间（秒）")


class BrowserActionResult(BaseModel):
    """浏览器子代理执行结果。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    action_type: BrowserActionType
    success: bool
    url: str | None = None
    title: str | None = None
    text_content: str | None = None
    screenshot_artifact_id: str | None = None
    error: str | None = None


class DesktopLock(BaseModel):
    """单屏桌面独占互斥锁（ADR-0248 allocateWindow / freeWindow 契约）。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str = Field(..., description="持有锁的 Agent/子代理 ID")
    session_id: str = Field(..., description="所属会话 ID")
    acquired_at_ms: int = Field(..., description="加锁时刻毫秒时间戳")
    ttl_seconds: int = Field(default=120, description="锁最大存活 TTL（防死锁）")

    def is_expired(self, current_time_ms: int) -> bool:
        """检查锁是否已超时。"""
        return current_time_ms >= (self.acquired_at_ms + self.ttl_seconds * 1000)
