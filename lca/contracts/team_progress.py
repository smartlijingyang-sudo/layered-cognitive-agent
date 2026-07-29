"""DelegationLedgerProtocol —— 团队委派进度台账接口。

跟踪 hierarchical 编排中每个角色的咨询状态，
为 CompletionPolicy 提供确定性判定依据。

具体实现（DelegationLedger）位于 layer1_cognitive/team_progress/。
Hooks 位于 layer1_cognitive/team_progress/hooks.py（ADR-0015 行为不进 contracts）。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.contracts.enums import RoleStatus


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
