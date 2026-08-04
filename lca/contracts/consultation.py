"""Lead consultation/board mandate control-plane session.

``ConsultationState`` is **only** for ``LeadMandate.CONSULT`` /
``LeadMandate.BOARD``:
required-role settlement, teammate roster for the lead prompt, and
delegate retry counters.

Free industry-style routing belongs in ``RoutingState``
(``LeadMandate.ROUTING``), not here.

It is intentionally **not** a generic multi-agent session bag.

Forbidden here (use strategy-local state or a dedicated session type instead):
- debate rounds / positions
- handoff chains
- group-chat speaker queues
- graph execution cursors
- free-form ``extra`` team fields

Field whitelist is frozen for architecture tests.
Adding a field requires updating ``CONSULTATION_FIELD_WHITELIST``.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Final

from lca.contracts.member_status import MemberStatus
from lca.contracts.role_team import RoleProfile

# Locked surface of hierarchical consultation. CI fails if the dataclass
# grows fields without an explicit whitelist update.
CONSULTATION_FIELD_WHITELIST: Final[frozenset[str]] = frozenset(
    {
        "member_status",
        "teammates",
        "delegate_max_attempts",
        "delegate_attempts",
    }
)


@dataclass
class ConsultationState:
    """Hierarchical supervisor session for one team run.

    Present only when an agent acts as hierarchical supervisor;
    solo / member runs keep ``AgentState.consultation is None``.

    Mutability:
    - mutated during the loop: ``member_status``, ``delegate_attempts``
    - fixed after injection: ``teammates``, ``delegate_max_attempts``
    """

    member_status: MemberStatus
    teammates: list[RoleProfile] = field(default_factory=list)
    delegate_max_attempts: int = 3
    delegate_attempts: dict[str, int] = field(default_factory=dict)


def assert_consultation_field_whitelist() -> None:
    """Raise AssertionError if ConsultationState fields drift from whitelist."""
    actual = {f.name for f in fields(ConsultationState)}
    if actual != CONSULTATION_FIELD_WHITELIST:
        missing = CONSULTATION_FIELD_WHITELIST - actual
        extra = actual - CONSULTATION_FIELD_WHITELIST
        raise AssertionError(
            "ConsultationState field surface drifted from the whitelist. "
            f"missing={sorted(missing)} extra={sorted(extra)}. "
            "Update CONSULTATION_FIELD_WHITELIST only after confirming the field "
            "is hierarchical settlement state — not another team lead session "
            "concern."
        )
