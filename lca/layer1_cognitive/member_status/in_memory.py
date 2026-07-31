"""InMemoryMemberStatus — default immutable MemberStatus board."""

from __future__ import annotations

from dataclasses import dataclass, field

from lca.contracts.enums import RoleStatus


@dataclass(frozen=True)
class InMemoryMemberStatus:
    """Immutable board of required member consult status.

    ``mark()`` returns a new instance (frozen dataclass).
    """

    required_roles: frozenset[str]
    status: dict[str, RoleStatus] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for role in self.required_roles:
            if role not in self.status:
                object.__setattr__(self, "status", {**self.status, role: RoleStatus.PENDING})

    def mark(self, role: str, new_status: RoleStatus) -> InMemoryMemberStatus:
        updated = {**self.status, role: new_status}
        return InMemoryMemberStatus(required_roles=self.required_roles, status=updated)

    def all_done(self) -> bool:
        return all(self.status.get(r) == RoleStatus.DONE for r in self.required_roles)

    def waiting_roles(self) -> list[str]:
        return [r for r in self.required_roles if self.status.get(r) != RoleStatus.DONE]

    def as_prompt_text(self) -> str:
        waiting = self.waiting_roles()
        if waiting:
            return f"尚未咨询的角色: {', '.join(waiting)}"
        return "所有必需角色均已咨询完毕"


# Transitional alias — remove after one release cycle.
DelegationLedger = InMemoryMemberStatus
