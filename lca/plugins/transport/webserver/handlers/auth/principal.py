"""统一身份模型 Principal 定义（修订 ADR-0252 D4 / C13 信息血统闭合）。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Principal(BaseModel):
    """全仓跨边界传递的统一可信身份模型（修订 ADR-0252 D4 / C13 强类型闭合）。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    issuer: str  # "mangli" | "lobehub" | "system"
    subject: str  # 用户唯一标识 (对应 userId 或工号)
    user_id: str = ""  # 用户ID (userId)
    name: str = ""  # 用户姓名
    mobile: str = ""  # 用户手机号码
    email: str = ""  # 用户邮箱地址
    job_number: str = ""  # 用户工号 (jobNumber)
    job_name: str = ""  # 岗位名称 (jobName)
    department: str = ""  # 部门 (department)
    clock_in_type: int | None = None  # 考勤打卡类型 (clockInType)
    ticket: str = ""  # 用户当前登录令牌 (ticket)
    dept_id: str | None = None  # 部门ID兼容字段
    roles: tuple[str, ...] = ()
    project_id: str | None = None  # 外部租户项目标签


__all__ = ["Principal"]
