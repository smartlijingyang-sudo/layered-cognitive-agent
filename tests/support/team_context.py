"""Test helpers: TeamContext with InternalTransport for mock members."""

from __future__ import annotations

from collections.abc import Sequence
from unittest.mock import MagicMock

from lca.contracts.decision import Observation
from lca.contracts.protocols import TeamContext
from lca.contracts.role_team import TeamConfig
from lca.layer0_infra.transport.agent_transport import InternalTransport


def _ensure_string_role(member: object, fallback: str) -> str:
    """MagicMock auto-attributes are not real roles — force a concrete str."""
    profile = getattr(member, "role_profile", None)
    role = getattr(profile, "role", None) if profile is not None else None
    if isinstance(role, str) and role:
        return role
    if profile is None or isinstance(profile, MagicMock):
        member.role_profile = MagicMock()  # type: ignore[attr-defined]
    member.role_profile.role = fallback  # type: ignore[attr-defined]
    return fallback


def team_context_with_transport(
    members: Sequence[MagicMock | object],
    *,
    config: TeamConfig | None = None,
) -> TeamContext:
    """Register each member's run() on InternalTransport keyed by role."""
    transport = InternalTransport()
    for index, member in enumerate(members):
        role = _ensure_string_role(member, fallback=f"member-{index}")

        async def _handler(subtask: str, _m: object = member) -> Observation:
            result = await _m.run(subtask)  # type: ignore[attr-defined]
            return Observation.from_result(result)

        transport.register_agent(role, _handler)
    return TeamContext(members=list(members), transport=transport, config=config)
