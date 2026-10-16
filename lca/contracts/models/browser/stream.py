"""Browser streaming, takeover, and input contract models (INV-BROWSER-01)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class BrowserSessionStatus(StrEnum):
    """浏览器会话运行与接管状态枚举。"""

    IDLE = "idle"
    AGENT_RUNNING = "agent_running"
    WAITING_USER_CONTROL = "waiting_user_control"
    HUMAN_TAKEOVER = "human_takeover"
    CLOSED = "closed"


class BrowserInputEventType(StrEnum):
    """上行用户前端交互事件类型。"""

    MOUSE_MOVE = "mouse_move"
    MOUSE_DOWN = "mouse_down"
    MOUSE_UP = "mouse_up"
    WHEEL = "wheel"
    KEY_DOWN = "key_down"
    KEY_UP = "key_up"


class BrowserInputEvent(BaseModel):
    """上行用户输入事件载荷（前端 Canvas 映射到 CDP 的精简统一模型）。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    type: BrowserInputEventType = Field(..., description="事件动作类型")
    x: float = Field(default=0.0, description="视口坐标 X (归一化 0.0~1.0 或绝对像素)")
    y: float = Field(default=0.0, description="视口坐标 Y (归一化 0.0~1.0 或绝对像素)")
    button: str | None = Field(default=None, description="鼠标按键: left / right / middle")
    delta_x: float = Field(default=0.0, description="滚轮水平位移")
    delta_y: float = Field(default=0.0, description="滚轮垂直位移")
    key: str | None = Field(default=None, description="键盘字符键值")
    code: str | None = Field(default=None, description="键盘物理键码")
    text: str | None = Field(default=None, description="文本输入内容")


class BrowserControlActionType(StrEnum):
    """浏览器控制信令类型。"""

    NAVIGATE = "navigate"
    BACK = "back"
    FORWARD = "forward"
    RELOAD = "reload"
    TAKEOVER = "takeover"
    RELEASE = "release"


class BrowserControlAction(BaseModel):
    """浏览器控制面信令。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    type: BrowserControlActionType = Field(..., description="控制信令类型")
    url: str | None = Field(default=None, description="目标网页 URL（仅 navigate 必需）")


class BrowserSessionSummary(BaseModel):
    """浏览器会话摘要与状态快照。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    session_id: str = Field(..., description="浏览器会话唯一标识 ID")
    run_id: str | None = Field(default=None, description="关联的认知 Run ID")
    url: str = Field(default="about:blank", description="当前网页 URL")
    title: str = Field(default="New Tab", description="当前网页标题")
    status: BrowserSessionStatus = Field(default=BrowserSessionStatus.IDLE, description="当前运行状态")
    viewport_width: int = Field(default=1280, description="视口渲染宽度")
    viewport_height: int = Field(default=800, description="视口渲染高度")
    has_active_stream: bool = False


__all__ = [
    "BrowserControlAction",
    "BrowserControlActionType",
    "BrowserInputEvent",
    "BrowserInputEventType",
    "BrowserSessionStatus",
    "BrowserSessionSummary",
]
