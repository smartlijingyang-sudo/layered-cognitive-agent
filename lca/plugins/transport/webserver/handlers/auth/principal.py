"""统一身份模型 Principal 定义（修订 ADR-0252 D4 / C13 信息血统闭合）。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Principal(BaseModel):
    """全仓跨边界传递的统一可信身份模型（修订 ADR-0252 D4 / C13 强类型闭合）。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    issuer: str  # "mangli" | "lobehub" | "system"
    subject: str  # 用户工号或身份唯一标识 (例如 "U888" 或 "usr_lobe")
    dept_id: str | None = None
    roles: tuple[str, ...] = ()
    project_id: str | None = None  # 外部租户项目标签


__all__ = ["Principal"]
