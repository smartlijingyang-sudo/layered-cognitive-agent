"""Test helpers: closed TeamStage over InternalTransport for mock members."""

from __future__ import annotations

from collections.abc import Sequence
from unittest.mock import MagicMock

from lca.contracts.decision import Observation
from lca.contracts.protocols import TeamStage
from lca.layer0_infra.transport.agent_transport import InternalTransport
from lca.layer3_agent.member_invoke import TransportMemberInvoker


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


def stage_with_invoker(members: Sequence[MagicMock | object]) -> TeamStage:
    """Register each member's run() on InternalTransport keyed by role."""
    transport = InternalTransport()
    for index, member in enumerate(members):
        role = _ensure_string_role(member, fallback=f"member-{index}")

        async def _handler(subtask: str, _m: object = member) -> Observation:
            result = await _m.run(subtask)  # type: ignore[union-attr]
            return Observation.from_result(result)

        transport.register_agent(role, _handler)
    return TeamStage(members=tuple(members), invoker=TransportMemberInvoker(transport))
