"""DelegationLedgerProtocol —— 团队委派进度台账接口。

跟踪 hierarchical 编排中每个角色的咨询状态，
为 CompletionPolicy 提供确定性判定依据。

具体实现（DelegationLedger）位于 layer1_cognitive/team_progress/。
"""

from __future__ import annotations

from typing import Any, Literal, Protocol, runtime_checkable

RoleStatus = Literal["pending", "in_progress", "done", "failed"]


@runtime_checkable
class DelegationLedgerProtocol(Protocol):
    """团队委派进度台账接口。

    消费方（TypedState、CompletionPolicy 等）依赖此 Protocol，
    不直接依赖具体实现。
    """

    @property
    def mandatory_roles(self) -> frozenset[str]: ...

    @property
    def status(self) -> dict[str, RoleStatus]: ...

    def mark(self, role: str, new_status: RoleStatus) -> DelegationLedgerProtocol: ...

    def is_covered(self) -> bool: ...

    def pending_roles(self) -> list[str]: ...


async def ledger_tracking_hook(event_name: str, state: Any, **kwargs: Any) -> None:
    """post_act hook：委派完成后自动记账。

    仅在 state.team_progress 存在时生效（即 hierarchical 场景的 supervisor）。
    普通 Agent 和其他编排模式完全不受影响。
    """
    decision = kwargs.get("decision")
    observation = kwargs.get("observation")
    ledger = getattr(state, "team_progress", None)
    if decision is None or ledger is None:
        return
    if decision.action_type == "delegate" and decision.delegate_to is not None:
        role = decision.delegate_to.target_role
        if role and role in ledger.mandatory_roles:
            new_status = "done" if getattr(observation, "success", False) else "failed"
            state.team_progress = ledger.mark(role, new_status)


async def progress_injection_hook(event_name: str, state: Any, **kwargs: Any) -> None:
    """pre_think hook：将团队进度文本注入 working_memory，供 Prompt 渲染。"""
    ledger = getattr(state, "team_progress", None)
    if ledger is None:
        return
    pending = ledger.pending_roles()
    text = f"尚未咨询的角色: {', '.join(pending)}" if pending else "所有必需角色均已咨询完毕"
    state.working_memory["team_progress_text"] = text
