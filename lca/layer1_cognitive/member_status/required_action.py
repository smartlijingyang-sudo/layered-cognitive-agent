"""Consultation board → next allowed action (pure).

Single pure function deciding the consultation state machine step.
Producer (this module) and consumer (must_consult_all gate) both live in
layer1_cognitive — layer-private collaboration types stay out of contracts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from lca.contracts.member_status import MemberStatus


@dataclass(frozen=True)
class RequiredAction:
    """给定 board 状态,状态机唯一允许的下一步是什么。

    kind == "must_delegate": 存在未到终态(non-terminal)的必需角色。
        target_role 给出"如果要改写决策,应该改写成委派给谁"的规范目标。
    kind == "may_respond": 所有必需角色都到终态(DONE 或终态 FAILED)。
        RESPOND 被允许,即便部分角色以 FAILED 结束——这是刻意的降级行为
        (degradation by design),不是 gate 没拦住的 bug。
    """

    kind: Literal["must_delegate", "may_respond"]
    target_role: str | None = None


def compute_required_action(board: MemberStatus) -> RequiredAction:
    """根据 board 状态计算状态机唯一允许的下一步。"""
    waiting = board.waiting_roles()
    if waiting:
        return RequiredAction(kind="must_delegate", target_role=waiting[0])
    return RequiredAction(kind="may_respond")
