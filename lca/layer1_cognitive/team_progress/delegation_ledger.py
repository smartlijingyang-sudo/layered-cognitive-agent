"""DelegationLedger —— DelegationLedgerProtocol 的默认不可变实现。"""

from __future__ import annotations

from dataclasses import dataclass, field

from lca.contracts.enums import RoleStatus


@dataclass(frozen=True)
class DelegationLedger:
    """不可变团队委派进度台账。

    ``mark()`` 返回新实例（frozen dataclass），保证状态更新显式且可追溯。
    """

    mandatory_roles: frozenset[str]
    status: dict[str, RoleStatus] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for role in self.mandatory_roles:
            if role not in self.status:
                object.__setattr__(self, "status", {**self.status, role: RoleStatus.PENDING})

    def mark(self, role: str, new_status: RoleStatus) -> DelegationLedger:
        """不可变更新：返回新实例，原实例不变。"""
        updated = {**self.status, role: new_status}
        return DelegationLedger(mandatory_roles=self.mandatory_roles, status=updated)

    def is_covered(self) -> bool:
        """所有必需角色都已完成（done）。"""
        return all(self.status.get(r) == RoleStatus.DONE for r in self.mandatory_roles)

    def pending_roles(self) -> list[str]:
        """尚未完成的角色列表（保持 mandatory_roles 的迭代顺序）。"""
        return [r for r in self.mandatory_roles if self.status.get(r) != RoleStatus.DONE]
