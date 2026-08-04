"""SUPERVISOR-family free routing control plane.

``RoutingState`` is for dynamic PM-style supervisors: no full-roster
settlement invariant. Do **not** grow ``ConsultationState`` for this.

Field whitelist is locked for architecture tests — same discipline as
the consultation control plane.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Final

from lca.contracts.delegation import DelegationResult
from lca.contracts.role_team import RoleProfile

ROUTING_FIELD_WHITELIST: Final[frozenset[str]] = frozenset(
    {
        "teammates",
        "assigned_roles",
        "notes",
        "results",
    }
)


@dataclass
class RoutingState:
    """Freeform supervisor session for one team run.

    Present when ``SupervisorPlane.ROUTING``; solo/member keep None.
    - ``teammates``: fixed roster for prompt
    - ``assigned_roles``: soft log of who was already delegated to (advisory)
    - ``notes``: short freeform planner notes (optional)
    - ``results``: settled delegation ledger  — authoritative fact
      source for the supervisor prompt (MEMBER_REPORTS) and idempotent
      delegation. It is a factual record, **not** a settlement gate:
      routing keeps no MustConsultAllMembers invariant.
    """

    teammates: list[RoleProfile] = field(default_factory=list)
    assigned_roles: list[str] = field(default_factory=list)
    notes: str = ""
    results: list[DelegationResult] = field(default_factory=list)


def assert_routing_field_whitelist() -> None:
    """Raise AssertionError if RoutingState fields drift from whitelist."""
    actual = {f.name for f in fields(RoutingState)}
    if actual != ROUTING_FIELD_WHITELIST:
        missing = ROUTING_FIELD_WHITELIST - actual
        extra = actual - ROUTING_FIELD_WHITELIST
        raise AssertionError(
            "RoutingState field surface drifted from whitelist. "
            f"missing={sorted(missing)} extra={sorted(extra)}. "
            "Update ROUTING_FIELD_WHITELIST and ADR after confirming the field "
            "is free-routing state — not consultation settlement."
        )
