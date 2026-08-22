"""L4 facade for plan-bound Agent and Team construction."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from lca.contracts.atoms.enums import ActionScope, MemoryLayer
from lca.contracts.mechanisms.capability import MissingCapabilityError
from lca.contracts.models.team.team_coordination import Coordination, LeadMandate
from lca.contracts.protocols import SharedMemoryStore, TeamUnit
from lca.contracts.protocols.infra import AgentTransport
from lca.contracts.protocols.spec import (
    DEFAULT_DELEGATE_MAX_ATTEMPTS,
    AgentSpec,
    Governance,
    LeadSpec,
    TeamSpec,
)
from lca.layer0_infra.observability import BoundObservability
from lca.layer3_agent.team_handle import TeamHandle
from lca.plugins.composer.agent_assembly import PlanBoundAgentAssembler, promote_lead
from lca.plugins.composer.plan_binding import bind_team
from lca.plugins.composer.plan_composition_support import (
    _format_tools_xml,
    _render_available_skills,
    build_perceive_hub,
    resolve_observability,
    team_trace_profile,
)

if TYPE_CHECKING:
    from cordis import Context

    from lca.contracts.protocols import DecisionGate
    from lca.layer3_agent.cognitive_agent import CognitiveAgent


__all__ = [
    "_format_tools_xml",
    "_render_available_skills",
    "build_perceive_hub",
    "promote_lead",
    "spawn_agent",
    "spawn_lead",
    "spawn_member",
    "spawn_team",
]


def _ensure_scope(scope: Context | None) -> Context:
    if scope is not None:
        if not callable(getattr(scope, "inject", None)):
            raise TypeError("spawn scope must be a booted cordis Context with inject()")
        return scope
    from lca.layer4_app.api import get_or_create_default_ctx

    return get_or_create_default_ctx()


def _compiled_plan_from_scope(scope: Context) -> object:
    """Compile the resolved boot Profile for TeamGraph binding."""

    resolved = getattr(scope, "resolved_profile", None)
    if resolved is None:
        raise MissingCapabilityError("resolved_profile")
    from lca.harness.profile.plan_compiler import compile_plan

    return compile_plan(resolved)


def spawn_agent(
    spec: AgentSpec,
    *,
    action_scope: ActionScope = ActionScope.SOLO,
    team_channel: AgentTransport | None = None,
    decision_gate: DecisionGate | None = None,
    shared_store: SharedMemoryStore | None = None,
    scope: Context | None = None,
) -> CognitiveAgent:
    """Close one Agent through the boot profile's plan-bound adapter."""

    bound_scope = _ensure_scope(scope)
    return PlanBoundAgentAssembler().assemble_agent(
        spec,
        action_scope=action_scope,
        team_channel=team_channel,
        decision_gate=decision_gate,
        shared_store=shared_store,
        scope=bound_scope,
    )


def spawn_lead(
    spec: AgentSpec,
    *,
    transport: AgentTransport,
    mandate: LeadMandate,
    observability: BoundObservability | None = None,
    scope: Context | None = None,
) -> CognitiveAgent:
    """Close a lead Agent through the production assembly adapter."""

    bound_scope = _ensure_scope(scope)
    bound_observability = observability or resolve_observability(spec, bound_scope)
    return PlanBoundAgentAssembler().assemble_lead(
        spec,
        transport=transport,
        mandate=mandate,
        observability=bound_observability,
        scope=bound_scope,
    )


def spawn_member(
    spec: AgentSpec,
    *,
    shared_store: SharedMemoryStore | None = None,
    observability: BoundObservability | None = None,
    scope: Context | None = None,
) -> CognitiveAgent:
    """Close a team member through the production assembly adapter."""

    bound_scope = _ensure_scope(scope)
    bound_observability = observability or resolve_observability(spec, bound_scope)
    return PlanBoundAgentAssembler().assemble_member(
        spec,
        shared_store=shared_store,
        observability=bound_observability,
        scope=bound_scope,
    )


def _governance_from(lead: LeadSpec | None, coordination: Coordination | None) -> Governance:
    if lead is not None:
        if coordination is not None:
            raise ValueError("Team requires exactly one of lead= or coordination=")
        return lead
    if coordination is not None:
        return coordination
    raise ValueError("Team requires exactly one of lead= or coordination=")


def spawn_team(
    spec: TeamSpec | None = None,
    *,
    members: Sequence[AgentSpec] | None = None,
    lead: LeadSpec | None = None,
    coordination: Coordination | None = None,
    shared_memory_layers: Sequence[MemoryLayer] | None = None,
    delegate_max_attempts: int | None = None,
    observability: str | BoundObservability | None = None,
    scope: Context | None = None,
) -> TeamUnit:
    """Bind one TeamSpec to the booted Profile and close a TeamHandle."""

    bound_scope = _ensure_scope(scope)
    if spec is None:
        if members is None:
            raise ValueError("spawn_team requires spec= or members=")
        spec = TeamSpec(
            members=tuple(members),
            governance=_governance_from(lead, coordination),
            shared_memory_layers=tuple(shared_memory_layers or ()),
            delegate_max_attempts=(
                delegate_max_attempts
                if delegate_max_attempts is not None
                else DEFAULT_DELEGATE_MAX_ATTEMPTS
            ),
            observability=observability,
        )
    bound = bind_team(spec, _compiled_plan_from_scope(bound_scope), scope=bound_scope)
    graph = bound.graph
    lead_agent = graph.metadata.get("lead")
    return TeamHandle(
        graph.strategy,
        team_trace_profile(spec, graph),
        graph.observability,
        graph.members,
        lead_agent,
    )
