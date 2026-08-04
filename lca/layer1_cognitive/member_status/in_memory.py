"""InMemoryMemberStatus — default immutable MemberStatus board."""

from __future__ import annotations

from dataclasses import dataclass, field

from lca.contracts.enums import RoleStatus
from lca.contracts.role_status_rules import is_success_status, is_terminal_status


@dataclass(frozen=True)
class InMemoryMemberStatus:
    """Immutable board of required member consult status.

    ``role_order`` guarantees deterministic iteration order (problem D fix).
    ``required_roles`` property returns a ``frozenset`` for Protocol compatibility.
    ``mark()`` returns a new instance (frozen dataclass).

    This is a pure state container (dumb): it does not know about
    failure_kind, retry policies, or attempt counts.
    """

    role_order: tuple[str, ...]
    status: dict[str, RoleStatus] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if len(set(self.role_order)) != len(self.role_order):
            raise ValueError(f"role_order 含重复角色: {self.role_order}")
        for role in self.role_order:
            if role not in self.status:
                object.__setattr__(self, "status", {**self.status, role: RoleStatus.PENDING})

    @property
    def required_roles(self) -> frozenset[str]:
        return frozenset(self.role_order)

    def mark(self, role: str, new_status: RoleStatus) -> InMemoryMemberStatus:
        updated = {**self.status, role: new_status}
        return InMemoryMemberStatus(role_order=self.role_order, status=updated)

    def all_done(self) -> bool:
        return all(is_success_status(self.status[r]) for r in self.role_order)

    def all_terminal(self) -> bool:
        return all(is_terminal_status(self.status[r]) for r in self.role_order)

    def waiting_roles(self) -> list[str]:
        return [r for r in self.role_order if not is_terminal_status(self.status[r])]

    def as_prompt_text(self) -> str:
        waiting = self.waiting_roles()
        if waiting:
            return f"尚未咨询的角色: {', '.join(waiting)}"
        failed = [r for r in self.role_order if self.status[r] == RoleStatus.FAILED]
        if failed:
            return f"{', '.join(failed)} 角色多次尝试后仍不可用,本次结论不含该视角"
        return "所有必需角色均已咨询完毕"
