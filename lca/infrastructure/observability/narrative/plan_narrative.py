"""计划步模板 —— 按 strategy_key / mandate 生成 run 计划描述（ADR-0037）。

场景卡的渲染由 journal console 投影器承担（``console_render.render_scenario_card``）；
本模块只提供计划步文案模板，供 ``TeamRunStarted.plan_steps`` 与团队组合期使用。
"""

from __future__ import annotations

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
