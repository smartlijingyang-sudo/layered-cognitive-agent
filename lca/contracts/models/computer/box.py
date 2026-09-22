from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class ComputerPlane(StrEnum):
    """执行电脑平面枚举。"""

    BOX = "box"  # 员工电脑（对用户称“我的电脑”，默认沙箱）
    LOCAL = "local"  # 用户本机（对用户称“你的电脑”，需 ADR-0246 授权）


class ComputerPlaneMeta(BaseModel):
    """电脑平面元数据。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    plane: ComputerPlane
    display_name: str
    description: str
