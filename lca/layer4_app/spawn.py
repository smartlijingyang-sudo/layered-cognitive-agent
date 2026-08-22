"""Plan-bound L4 composition root for Agent and Team runnables."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import TYPE_CHECKING

from lca.contracts.atoms.enums import ActionScope, ComponentKind, MemoryLayer
from lca.contracts.mechanisms import consume
from lca.contracts.mechanisms.capability import MissingCapabilityError, require_capability
from lca.contracts.models.team.team_coordination import (
    Coordination,
    LeadMandate,
    gate_name_for_mandate,
)
from lca.contracts.protocols import BudgetPolicy, SharedMemoryStore, TeamUnit
from lca.contracts.protocols.infra import AgentTransport
from lca.contracts.protocols.spec import (
    DEFAULT_DELEGATE_MAX_ATTEMPTS,
    AgentSpec,
    Governance,
    LeadSpec,
    TeamSpec,
)
from lca.layer0_infra.observability import BoundObservability
from lca.layer2_runtime.runtime_loop import CognitiveRuntime
from lca.layer3_agent.cognitive_agent import CognitiveAgent
from lca.layer3_agent.team_handle import TeamHandle
from lca.layer4_app.policies import LEAD_BUDGET_POLICY_KEY
from lca.layer4_app.runtime_factory import RuntimeDeps, build_cognitive_runtime
from lca.plugins.composer.plan_composition_support import (
    AgentCompositionRequest,
    _format_tools_xml,
    _render_available_skills,
    build_perceive_hub,
    resolve_decision_gate,
    team_trace_profile,
)

if TYPE_CHECKING:
    from cordis import Context

    from lca.contracts.protocols import DecisionGate
    from lca.contracts.protocols.plan import CompiledRunPlan


__all__ = ["promote_lead", "spawn_agent", "spawn_lead", "spawn_member", "spawn_team"]


def _ensure_scope(scope: Context | None) -> Context:
    if scope is not None:
        if not callable(getattr(scope, "inject", None)):
            raise TypeError("spawn scope must be a booted cordis Context with inject()")
        return scope
    from lca.layer4_app.api import get_or_create_default_ctx

    return get_or_create_default_ctx()


def _compiled_plan_from_scope(scope: Context) -> CompiledRunPlan:
    """Compile the resolved boot Profile into the only runnable input plan."""

    resolved = getattr(scope, "resolved_profile", None)
    if resolved is None:
        raise MissingCapabilityError("resolved_profile")
    from lca.harness.profile.plan_compiler import compile_plan

    return compile_plan(resolved)


def _agent_from_bound_graph(
    spec: AgentSpec,
    graph: object,
    *,
    plan: CompiledRunPlan,
    plan_ref: str,
) -> CognitiveAgent:
    """Close a complete AgentGraph into a CognitiveAgent that interprets ``plan``."""

    required = (
        "brain",
        "body",
        "memory",
        "state_store",
        "perceive_hub",
        "hooks",
        "observability",
        "stop_rule",
    )
    missing = [field for field in required if getattr(graph, field, None) is None]
    if missing:
        raise MissingCapabilityError(
            "plan-bound AgentGraph is incomplete; missing " + ", ".join(missing)
        )
    runtime = build_cognitive_runtime(
        RuntimeDeps(
            brain=graph.brain,
            body=graph.body,
            memory=consume("memory", graph.memory, CognitiveRuntime),
            hooks=graph.hooks,
            state_store=consume("state_store", graph.state_store, CognitiveRuntime),
            perceive_hub=graph.perceive_hub,
            stop_rule=graph.stop_rule,
            control_plan=plan.control,
        )
    )
    return CognitiveAgent(
        runtime,
        spec.profile,
        graph.observability,
        max_steps=spec.max_steps,
        max_wall_clock_seconds=spec.max_wall_clock_seconds,
        plan_ref=plan_ref,
    )


def spawn_agent(
    spec: AgentSpec,
    *,
    action_scope: ActionScope = ActionScope.SOLO,
    team_channel: AgentTransport | None = None,
    decision_gate: DecisionGate | None = None,
    shared_store: SharedMemoryStore | None = None,
    scope: Context | None = None,
) -> CognitiveAgent:
    """Bind one AgentSpec to the booted Profile plan and return a live Agent."""

    bound_scope = _ensure_scope(scope)
    plan = _compiled_plan_from_scope(bound_scope)
    request = AgentCompositionRequest(
        spec=spec,
        action_scope=action_scope,
        team_channel=team_channel,
        decision_gate=decision_gate,
        shared_store=shared_store,
    )
    from lca.layer4_app.spawn_bind_plan import bind_plan

    bound = bind_plan(request, plan, scope=bound_scope)
    return _agent_from_bound_graph(spec, bound.graph, plan=bound.plan, plan_ref=bound.plan_ref)


def promote_lead(lead: CognitiveAgent, policy: BudgetPolicy) -> CognitiveAgent:
    """Apply the declared lead budget policy without changing the bound plan."""

    limits = policy.resolve(lead)
    return CognitiveAgent(
        lead.runtime,
        lead.role_profile,
        lead.observability,
        max_steps=limits.max_steps,
        max_wall_clock_seconds=limits.max_wall_clock_seconds,
        plan_ref=lead.plan_ref,
    )


def spawn_lead(
    spec: AgentSpec,
    *,
    transport: AgentTransport,
    mandate: LeadMandate,
    observability: BoundObservability | None = None,
    scope: Context | None = None,
) -> CognitiveAgent:
    """Bind a lead Agent through the same plan path as every other Agent."""

    bound_scope = _ensure_scope(scope)
    lead_spec = replace(spec, observability=observability) if observability is not None else spec
    agent = spawn_agent(
        lead_spec,
        action_scope=ActionScope.LEAD,
        team_channel=transport,
        decision_gate=resolve_decision_gate(gate_name_for_mandate(mandate), scope=bound_scope),
        scope=bound_scope,
    )
    components = require_capability(bound_scope, "component_registry")
    policy = components.require(ComponentKind.BUDGET_POLICY, LEAD_BUDGET_POLICY_KEY)()
    if not isinstance(policy, BudgetPolicy):
        raise TypeError(f"lead budget policy must be BudgetPolicy, got {type(policy).__name__}")
    return promote_lead(agent, policy)


def spawn_member(
    spec: AgentSpec,
    *,
    shared_store: SharedMemoryStore | None = None,
    observability: BoundObservability | None = None,
    scope: Context | None = None,
) -> CognitiveAgent:
    """Bind a member Agent through the plan path with its declared shared memory."""

    member_spec = replace(spec, observability=observability) if observability is not None else spec
    return spawn_agent(
        member_spec,
        action_scope=ActionScope.MEMBER,
        shared_store=shared_store,
        scope=scope,
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
    """Bind one TeamSpec to the booted Profile plan and return a TeamHandle."""

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
    from lca.layer4_app.spawn_bind_plan import bind_team

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
