"""Consultation board → next allowed action (pure).

Single pure function deciding the consultation state machine step.
Producer (this module) and consumer (must_consult_all gate) both live in
layer1_cognitive — layer-private collaboration types stay out of contracts.

ADR-0049：优先走证据驱动的 ``compute_consult_next``；本模块保留
``RequiredAction`` 薄适配，兼容既有 gate/测试。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from lca.contracts.models.core.state import AgentState, Budget
from lca.contracts.models.team.member_status import MemberStatus
from lca.contracts.models.team.team_awareness import ConsultDuty
from lca.cognition.member_status.consult_policy import (
    ConsultNextAction,
    compute_consult_next,
    compute_required_action_from_duty,
)


@dataclass(frozen=True)
class RequiredAction:
    """给定 board 状态,状态机唯一允许的下一步是什么。

    kind == "must_delegate": 存在未到终态(non-terminal)的必需角色。
        target_role 给出"如果要改写决策,应该改写成委派给谁"的规范目标。
        target_roles 给出并行 fan-out 全集（ADR-0049）。
    kind == "may_respond": 所有必需角色都到终态(DONE / DONE_PARTIAL / FAILED)。
        RESPOND 被允许,即便部分角色以 FAILED 结束——这是刻意的降级行为
        (degradation by design),不是 gate 没拦住的 bug。
    """

    kind: Literal["must_delegate", "may_respond"]
    target_role: str | None = None
    target_roles: tuple[str, ...] = ()


def compute_required_action(board: MemberStatus) -> RequiredAction:
    """根据 board 状态计算状态机唯一允许的下一步（无证据时的兼容入口）。"""
    waiting = board.waiting_roles()
    if waiting:
        return RequiredAction(
            kind="must_delegate",
            target_role=waiting[0],
            target_roles=tuple(waiting),
        )
    return RequiredAction(kind="may_respond")


def compute_required_action_rich(
    duty: ConsultDuty, state: AgentState | None = None
) -> ConsultNextAction:
    """证据驱动入口；state 缺失时用空 Budget 占位（仅测 board 进度）。"""
    if state is None:
        state = AgentState(trace_id="policy", task="", budget=Budget())
    if duty.member_status.all_terminal():
        return compute_required_action_from_duty(duty, state)
    return compute_consult_next(duty, state)
