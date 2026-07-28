"""DelegationLedger —— 团队委派进度台账。

跟踪 hierarchical 编排中每个角色的咨询状态，
为 CompletionPolicy 提供确定性判定依据。
"""

from __future__ import annotations

from dataclasses import dataclass, field
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


@dataclass(frozen=True)
class DelegationLedger:
    """不可变团队委派进度台账（DelegationLedgerProtocol 的默认实现）。

    ``mark()`` 返回新实例（frozen dataclass），保证状态更新显式且可追溯。
    """

    mandatory_roles: frozenset[str]
    status: dict[str, RoleStatus] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for role in self.mandatory_roles:
            if role not in self.status:
                object.__setattr__(self, "status", {**self.status, role: "pending"})

    def mark(self, role: str, new_status: RoleStatus) -> DelegationLedger:
        """不可变更新：返回新实例，原实例不变。"""
        updated = {**self.status, role: new_status}
        return DelegationLedger(mandatory_roles=self.mandatory_roles, status=updated)

    def is_covered(self) -> bool:
        """所有必需角色都已完成（done）。"""
        return all(self.status.get(r) == "done" for r in self.mandatory_roles)

    def pending_roles(self) -> list[str]:
        """尚未完成的角色列表（保持 mandatory_roles 的迭代顺序）。"""
        return [r for r in self.mandatory_roles if self.status.get(r) != "done"]


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
