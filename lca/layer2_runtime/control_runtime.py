"""CompiledRunPlan 控制面的运行时解释器。

`ControlPlan` 是不可变声明；本模块将其投影为某一循环阶段的有序有效投稿。
解释器只求值受限 Activation DSL，不执行插件代码，也不修改运行计划。执行层通过
`ControlSelection` 读取已激活条目并保留选择证据。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols.control_plan import Activation, ControlEntry, ControlPlan, slot_entries


@dataclass(frozen=True, slots=True)
class ControlSelection:
    """一个槽位在当前阶段的确定性选择结果。"""

    slot: ControlSlot
    entries: tuple[ControlEntry, ...]
    facts: Mapping[str, Any]


def select_control_entries(
    plan: ControlPlan,
    slot: ControlSlot,
    state: AgentState,
    *,
    facts: Mapping[str, Any] | None = None,
) -> ControlSelection:
    """返回满足 Activation 的、按计划顺序排列的槽位投稿。"""
    merged_facts = control_facts(state, extra=facts)
    selected = tuple(
        entry
        for entry in slot_entries(plan, slot)
        if evaluate_activation(entry.activation, merged_facts)
    )
    return ControlSelection(slot=slot, entries=selected, facts=merged_facts)


def control_facts(
    state: AgentState,
    *,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """构建 Activation DSL 唯一允许读取的运行期事实快照。"""
    budget = state.budget
    facts: dict[str, Any] = {
        "task": state.task,
        "state.step": state.step,
        "state.status": state.status.value,
        "state.agent_role": state.agent_role,
        "state.wall_clock": budget.max_wall_clock_seconds,
        "state.budget.max_steps": budget.max_steps,
        "state.budget.used_steps": budget.used_steps,
    }
    if extra:
        facts.update(extra)
    return facts


def evaluate_activation(activation: Activation, facts: Mapping[str, Any]) -> bool:
    """在事实快照上求值经过 resolver 校验的 Activation DSL。"""
    return _evaluate_node(activation.predicate, facts)


def _evaluate_node(node: Mapping[str, Any], facts: Mapping[str, Any]) -> bool:
    if "always" in node:
        return True
    if "all" in node:
        return all(_evaluate_node(item, facts) for item in node["all"])
    if "any" in node:
        return any(_evaluate_node(item, facts) for item in node["any"])
    if "not" in node:
        return not _evaluate_node(node["not"], facts)

    value = facts.get(str(node["fact"]))
    if "exists" in node:
        return value is not None
    if "missing" in node:
        return value is None
    if "eq" in node:
        return value == node["eq"]
    if "ne" in node:
        return value != node["ne"]
    if "in" in node:
        return value in node["in"]
    if "not_in" in node:
        return value not in node["not_in"]
    if value is None:
        return False
    if "lt" in node:
        return value < node["lt"]
    if "le" in node:
        return value <= node["le"]
    if "gt" in node:
        return value > node["gt"]
    if "ge" in node:
        return value >= node["ge"]
    raise ValueError(f"unsupported validated activation predicate: {node!r}")


__all__ = [
    "ControlSelection",
    "control_facts",
    "evaluate_activation",
    "select_control_entries",
]
