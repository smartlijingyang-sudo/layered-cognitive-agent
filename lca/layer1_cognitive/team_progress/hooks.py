"""团队进度相关生命周期 hooks（从 contracts 迁出，ADR-0015 收口）。"""

from __future__ import annotations

from typing import Any

from lca.contracts.enums import ActionType, RoleStatus
from lca.contracts.state import TypedState


async def ledger_tracking_hook(event_name: str, state: TypedState, **kwargs: Any) -> None:
    """post_act hook：委派完成后自动记账。

    仅在 state.team_progress 存在时生效（hierarchical supervisor）。
    """
    decision = kwargs.get("decision")
    observation = kwargs.get("observation")
    ledger = getattr(state, "team_progress", None)
    if decision is None or ledger is None:
        return
    if decision.action_type == ActionType.DELEGATE and decision.delegate_to is not None:
        role = decision.delegate_to.target_role
        if role and role in ledger.mandatory_roles:
            new_status = (
                RoleStatus.DONE if getattr(observation, "success", False) else RoleStatus.FAILED
            )
            state.team_progress = ledger.mark(role, new_status)


async def progress_injection_hook(event_name: str, state: TypedState, **kwargs: Any) -> None:
    """pre_think hook：将团队进度文本写入 TypedState.team_progress_text。"""
    ledger = getattr(state, "team_progress", None)
    if ledger is None:
        return
    pending = ledger.pending_roles()
    text = f"尚未咨询的角色: {', '.join(pending)}" if pending else "所有必需角色均已咨询完毕"
    state.team_progress_text = text
