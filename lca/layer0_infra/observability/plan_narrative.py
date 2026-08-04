"""Run-plan 场景卡叙事（run.plan span → 人类可读横幅）。

按 strategy_key / mandate 提供计划步骤模板，并把 RUN_PLAN span 渲染成
``┌──┐`` 卡片。实时 span 行渲染在 ``run_narrative.py``。
"""

from __future__ import annotations

from lca.contracts.observability import TraceSpan
from lca.contracts.telemetry import (
    ATTR_AGENT_ROLE,
    ATTR_LEAD_ROLE,
    ATTR_MANDATE,
    ATTR_MEMBERS,
    ATTR_OBJECTIVE_PREVIEW,
    ATTR_PLAN_STEPS,
    ATTR_STRATEGY_KEY,
    ATTR_TEAM_ID,
)
from lca.layer0_infra.observability.narrative_utils import attr_text, wrap_words

# Generic plan templates by strategy_key (coordination / lead family).
_STRATEGY_PLAN: dict[str, tuple[str, ...]] = {
    "lead": (
        "1. Lead 阅读目标并决策（委派 / 咨询 / 自答）",
        "2. 按 mandate 调用成员（transport / member_invoke）",
        "3. Lead 收口并给出最终答复",
    ),
    "pipeline": (
        "1. 第 1 位成员处理目标",
        "2. 依次接力后续成员",
        "3. 最后一位输出最终结果",
    ),
    "fan_out": (
        "1. 并行调用全部成员",
        "2. 收集候选输出",
        "3. 合成最终结果",
    ),
    "peer_relay": (
        "1. 从首位成员开始",
        "2. 点对点 relay",
        "3. 得到可结束答复后停止",
    ),
    "peer_swarm": (
        "1. 开启对等多轮",
        "2. 成员轮流发言",
        "3. 达轮次上限或收敛后结束",
    ),
    "debate": (
        "1. 开启辩论轮次",
        "2. 双方交替陈述",
        "3. 收敛或超时结束",
    ),
    "graph": (
        "1. 从图 ENTRY 进入",
        "2. 按边执行 AGENT 节点",
        "3. 到达 EXIT 结束",
    ),
    "solo": (
        "1. perceive 感知任务",
        "2. think（LLM）决策",
        "3. act → reflect → complete",
    ),
}

_MANDATE_NOTE: dict[str, str] = {
    "routing": "mandate=routing：Lead 显式委派成员后收口",
    "consult": "mandate=consult：Lead 可咨询成员后自决",
    "board": "mandate=board：全员咨询后 Lead 收口",
}

_CARD_WIDTH = 58
_TASK_WIDTH = 54
_NO_STRATEGY = "—"


def strategy_plan_steps(strategy_key: str, mandate: str | None = None) -> tuple[str, ...]:
    key = strategy_key or "solo"
    base = _STRATEGY_PLAN.get(key, _STRATEGY_PLAN["solo"])
    if key == "lead" and mandate:
        note = _MANDATE_NOTE.get(mandate)
        if note:
            return (note, *base)
    return base


def plan_steps_joined(strategy_key: str, mandate: str | None = None) -> str:
    return " | ".join(strategy_plan_steps(strategy_key, mandate))


def format_run_plan_card(span: TraceSpan) -> str:
    """Banner for SpanName.RUN_PLAN — who / strategy / objective / steps."""
    attrs = span.attributes or {}
    strategy = attr_text(attrs, ATTR_STRATEGY_KEY) or _NO_STRATEGY
    mandate = attr_text(attrs, ATTR_MANDATE)
    members = attr_text(attrs, ATTR_MEMBERS)
    lead = attr_text(attrs, ATTR_LEAD_ROLE)
    team_id = attr_text(attrs, ATTR_TEAM_ID)
    role = attr_text(attrs, ATTR_AGENT_ROLE)
    objective = attr_text(attrs, ATTR_OBJECTIVE_PREVIEW)
    plan_raw = attr_text(attrs, ATTR_PLAN_STEPS)
    steps = (
        [s.strip() for s in plan_raw.split("|") if s.strip()]
        if plan_raw
        else list(
            strategy_plan_steps(strategy if strategy != _NO_STRATEGY else "solo", mandate or None)
        )
    )

    title = _card_title(role, strategy, members)
    lines = ["", "┌" + "─" * _CARD_WIDTH + "┐", f"│ {title}"]
    meta = _card_meta(team_id, strategy, mandate, lead, members, role)
    if meta:
        lines.append("│ " + "  ".join(meta))
    lines.append("│")
    lines.append("│ plan")
    for s in steps:
        lines.append(f"│   {s}")
    if objective:
        lines.append("│")
        lines.append("│ task")
        for chunk in wrap_words(objective, _TASK_WIDTH):
            lines.append(f"│   {chunk}")
    lines.append("└" + "─" * _CARD_WIDTH + "┘")
    return "\n".join(lines)


def _card_title(role: str, strategy: str, members: str) -> str:
    if role and not members:
        return f"Agent  ·  {role}"
    if strategy and strategy != _NO_STRATEGY:
        return f"Team   ·  strategy={strategy}"
    return "Run"


def _card_meta(
    team_id: str, strategy: str, mandate: str, lead: str, members: str, role: str
) -> list[str]:
    meta: list[str] = []
    if team_id:
        meta.append(f"team={team_id}")
    if strategy and strategy != _NO_STRATEGY:
        meta.append(f"strategy={strategy}")
    if mandate:
        meta.append(f"mandate={mandate}")
    if lead:
        meta.append(f"lead={lead}")
    if members:
        meta.append(f"members={members}")
    if role and not members:
        meta.append(f"role={role}")
    return meta
