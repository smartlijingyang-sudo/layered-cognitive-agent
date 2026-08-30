"""团队 trace 档案 —— 团队级静态属性装配（ADR-0034/0037）。

遥测与行为分离：组合根从组合期已知的角色画像装配一份不可变
``TeamTraceProfile``；运行边缘（``TeamHandle.run``）只消费它 record
``TeamRunStarted``（场景卡随事件投影），不临时拼 attrs、不做 getattr 反射。
"""

from __future__ import annotations

from dataclasses import dataclass

_OBJECTIVE_PREVIEW_MAX = 240
"""目标文本在 span 属性中的展示长度上限（solo / team 场景卡共用）。"""


@dataclass(frozen=True)
class TeamTraceProfile:
    """一个封闭团队的静态档案（全部字段在组合期派生完毕）。

    - ``mandate``：LeadMandate 的字符串值；无 lead 团队为 None。
    - ``lead_role``：lead 角色名；无 lead 团队为 ""。
    """

    team_id: str
    strategy_key: str
    mandate: str | None
    lead_role: str
    member_roles: tuple[str, ...]


def team_id_for(strategy_key: str) -> str:
    """team_id 生成规则：``team-{strategy_key}``。"""
    return f"team-{strategy_key}"


def objective_preview(text: str) -> str:
    """截断目标文本用于展示。"""
    return text[:_OBJECTIVE_PREVIEW_MAX]
