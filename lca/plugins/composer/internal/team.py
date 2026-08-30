"""Collaboration-cluster assembly helpers for plan-bound graph composition."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from lca.contracts.atoms.enums import DecisionGateName
from lca.contracts.capabilities import GATES, OBSERVABILITY
from lca.contracts.mechanisms.capability import require_capability
from lca.contracts.protocols import DecisionGate, ObservabilityBackend
from lca.contracts.protocols.infra import AgentTransport, TransportRegistryProtocol
from lca.contracts.protocols.spec import AgentSpec, LeadSpec, TeamSpec, strategy_key_for_governance
from lca.layer0_infra.observability import BoundObservability, TeamTraceProfile, team_id_for

if TYPE_CHECKING:
    from lca.contracts.harness.composer import TeamGraph


def resolve_decision_gate(name: DecisionGateName, *, scope: object) -> DecisionGate | None:
    """Resolve a Lead's closed-set gate choice through the Gate service only."""

    if name == DecisionGateName.NONE:
        return None
    return cast("DecisionGate", require_capability(scope, GATES.key).create(name.value))


def fork_transport(
    parent: TransportRegistryProtocol,
    extra: AgentTransport | None,
    scope: object,
) -> TransportRegistryProtocol:
    """Fork inherited transports and select at most one local replacement.

    A Team-level transport is composition input rather than a second provider.
    When it owns an inherited protocol, the inherited entry is omitted before
    the local implementation is registered, keeping replacement local to this
    collaboration seam instead of relying on provider order.
    """

    factory = require_capability(scope, "transport.compose_service")
    child = cast("TransportRegistryProtocol", factory())
    extra_protocol = extra.protocol_name if extra is not None else None
    for protocol in parent.list_protocols():
        if protocol != extra_protocol:
            child.register(parent.resolve(protocol))
    if extra is not None:
        child.register(extra)
    return child


def resolve_observability(spec: AgentSpec, scope: object) -> BoundObservability:
    """Resolve one Agent's already-bound observability implementation."""

    if isinstance(spec.observability, BoundObservability):
        return spec.observability
    if isinstance(spec.observability, str):
        return _default_observability(scope)
    raise TypeError(
        "AgentSpec.observability must resolve to BoundObservability in plan composition"
    )


def resolve_team_observability(spec: TeamSpec, scope: object) -> BoundObservability:
    """Use an explicitly bound team or member observability implementation first."""

    candidates: list[str | ObservabilityBackend | BoundObservability] = []
    if spec.observability is not None:
        candidates.append(spec.observability)
    candidates.extend(member.observability for member in spec.members)
    if isinstance(spec.governance, LeadSpec):
        candidates.append(spec.governance.agent.observability)
    for candidate in candidates:
        if isinstance(candidate, BoundObservability):
            return candidate
    return _default_observability(scope)


def team_trace_profile(spec: TeamSpec, graph: TeamGraph) -> TeamTraceProfile:
    """Project the fully bound Team graph into a stable observability profile."""

    lead = graph.lead
    strategy_key = strategy_key_for_governance(spec.governance)
    mandate = spec.governance.mandate.value if isinstance(spec.governance, LeadSpec) else None
    return TeamTraceProfile(
        team_id=team_id_for(strategy_key),
        strategy_key=strategy_key,
        mandate=mandate,
        lead_role=lead.role_profile.role if lead is not None else "",
        member_roles=tuple(member.role_profile.role for member in graph.members),
    )


def _default_observability(scope: object) -> BoundObservability:
    """Resolve the profile-level observability binding exactly once per caller."""

    return cast("BoundObservability", require_capability(scope, OBSERVABILITY.key))


__all__ = [
    "fork_transport",
    "resolve_decision_gate",
    "resolve_observability",
    "resolve_team_observability",
    "team_trace_profile",
]
