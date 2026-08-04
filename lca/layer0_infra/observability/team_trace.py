"""团队 trace 档案 —— 团队级静态 span 属性与装配（ADR-0034）。

遥测与行为分离：组合根从组合期已知的角色画像装配一份不可变
``TeamTraceProfile``；运行边缘（``TeamHandle.run``）只消费它发出
``run.team`` / ``run.plan`` 场景卡，不再临时拼 attrs、不做 getattr 反射。
属性键值与旧模型逐字节一致，console / jsonl 输出保持兼容。
"""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.telemetry import (
    ATTR_LEAD_ROLE,
    ATTR_MANDATE,
    ATTR_MEMBERS,
    ATTR_OBJECTIVE_PREVIEW,
    ATTR_PLAN_STEPS,
    ATTR_STRATEGY_KEY,
    ATTR_TEAM_ID,
)
from lca.layer0_infra.observability.plan_narrative import plan_steps_joined

_OBJECTIVE_PREVIEW_MAX = 240
"""目标文本在 span 属性中的展示长度上限（solo / team 场景卡共用）。"""


@dataclass(frozen=True)
class TeamTraceProfile:
    """一个封闭团队的静态 span 档案（全部字段在组合期派生完毕）。

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
    """截断目标文本用于 span 展示。"""
    return text[:_OBJECTIVE_PREVIEW_MAX]


def team_run_attrs(profile: TeamTraceProfile) -> dict[str, object]:
    """``run.team`` 根 span 属性。"""
    attrs: dict[str, object] = {
        ATTR_TEAM_ID: profile.team_id,
        ATTR_STRATEGY_KEY: profile.strategy_key,
    }
    if profile.mandate is not None:
        attrs[ATTR_MANDATE] = profile.mandate
    return attrs


def plan_card_attrs(profile: TeamTraceProfile, objective_text: str) -> dict[str, object]:
    """``run.plan`` 场景卡 span 属性。"""
    attrs: dict[str, object] = {
        ATTR_TEAM_ID: profile.team_id,
        ATTR_STRATEGY_KEY: profile.strategy_key,
        ATTR_MEMBERS: ",".join(profile.member_roles),
        ATTR_OBJECTIVE_PREVIEW: objective_preview(objective_text),
        ATTR_PLAN_STEPS: plan_steps_joined(profile.strategy_key, profile.mandate),
    }
    if profile.mandate is not None:
        attrs[ATTR_MANDATE] = profile.mandate
    if profile.lead_role:
        attrs[ATTR_LEAD_ROLE] = profile.lead_role
    return attrs
