"""MemberStatus — which required team members still need to be consulted.

Single source of truth for hierarchical “must consult all” progress.
Prompt text is derived via ``as_prompt_text()`` — never cached as a second field.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.contracts.enums import RoleStatus


@runtime_checkable
class MemberStatus(Protocol):
    """Board of required member roles and their consult status."""

    @property
    def required_roles(self) -> frozenset[str]: ...

    @property
    def status(self) -> dict[str, RoleStatus]: ...

    def mark(self, role: str, new_status: RoleStatus) -> MemberStatus: ...

    def all_done(self) -> bool: ...

    def waiting_roles(self) -> list[str]: ...

    def as_prompt_text(self) -> str: ...
