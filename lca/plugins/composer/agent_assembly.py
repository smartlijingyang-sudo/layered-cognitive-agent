"""Plan-bound Agent assembly used by the TeamComposer recursion seam."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Protocol, cast

from lca.contracts.atoms.enums import ActionScope
from lca.contracts.capabilities import LEAD_BUDGET_POLICY_RESOLVER
from lca.contracts.mechanisms.capability import require_capability
from lca.contracts.models.team.team_coordination import LeadMandate, gate_name_for_mandate
from lca.contracts.protocols import BudgetPolicy, LeadBudgetPolicyResolver, SharedMemoryStore
from lca.contracts.protocols.infra import AgentTransport
from lca.contracts.protocols.spec import AgentSpec
from lca.infrastructure.observability import BoundObservability
from lca.layer3_agent.cognitive_agent import CognitiveAgent
from lca.plugins.composer.internal.team import resolve_decision_gate
from lca.plugins.composer.plan_binding import bind_agent_from_scope
from lca.plugins.composer.runtime_assembly import assemble_runtime_from_graph

if TYPE_CHECKING:
    from cordis import Context

    from lca.contracts.harness.composer import AgentGraph
    from lca.contracts.protocols import DecisionGate
    from lca.contracts.protocols.plan import CompiledRunPlan


class AgentAssemblyPort(Protocol):
    """Narrow recursion seam consumed by TeamComposer."""

    def assemble_member(
        self,
        spec: AgentSpec,
        *,
        shared_store: SharedMemoryStore | None,
        observability: BoundObservability,
        scope: Context,
    ) -> CognitiveAgent: ...

    def assemble_lead(
        self,
        spec: AgentSpec,
        *,
        transport: AgentTransport,
        mandate: LeadMandate,
        observability: BoundObservability,
        scope: Context,
    ) -> CognitiveAgent: ...


class PlanBoundAgentAssembler(AgentAssemblyPort):
    """Production adapter that closes Agents from the booted profile plan."""

    def assemble_agent(
        self,
        spec: AgentSpec,
        *,
        action_scope: ActionScope = ActionScope.SOLO,
        team_channel: AgentTransport | None = None,
        decision_gate: DecisionGate | None = None,
        shared_store: SharedMemoryStore | None = None,
        scope: Context,
    ) -> CognitiveAgent:
        """Bind the booted profile plan and close one Agent."""

        bound = bind_agent_from_scope(
            spec,
            action_scope=action_scope,
            team_channel=team_channel,
            decision_gate=decision_gate,
            shared_store=shared_store,
            scope=scope,
        )
        return _agent_from_bound_graph(
            spec,
            bound.graph,
            plan=bound.plan,
            plan_ref=bound.plan_ref,
            scope=scope,
        )

    def assemble_member(
        self,
        spec: AgentSpec,
        *,
        shared_store: SharedMemoryStore | None,
        observability: BoundObservability,
        scope: Context,
    ) -> CognitiveAgent:
        """Assemble a team member through the same plan-bound path as solo Agents."""

        member_spec = replace(spec, observability=observability)
        return self.assemble_agent(
            member_spec,
            action_scope=ActionScope.MEMBER,
            shared_store=shared_store,
            scope=scope,
        )

    def assemble_lead(
        self,
        spec: AgentSpec,
        *,
        transport: AgentTransport,
        mandate: LeadMandate,
        observability: BoundObservability,
        scope: Context,
    ) -> CognitiveAgent:
        """Assemble and promote a lead without leaking plan binding to TeamComposer."""

        lead_spec = replace(spec, observability=observability)
        lead = self.assemble_agent(
            lead_spec,
            action_scope=ActionScope.LEAD,
            team_channel=transport,
            decision_gate=resolve_decision_gate(gate_name_for_mandate(mandate), scope=scope),
            scope=scope,
        )
        policy_resolver = require_capability(scope, LEAD_BUDGET_POLICY_RESOLVER.key)
        if not isinstance(policy_resolver, LeadBudgetPolicyResolver):
            raise TypeError(
                "lead_budget_policy_resolver must implement LeadBudgetPolicyResolver, "
                f"got {type(policy_resolver).__name__}"
            )
        return promote_lead(lead, policy_resolver.resolve_policy())


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


def _agent_from_bound_graph(
    spec: AgentSpec,
    graph: AgentGraph,
    *,
    plan: CompiledRunPlan,
    plan_ref: str,
    scope: Context,
) -> CognitiveAgent:
    """Close the plan-bound complete AgentGraph into a CognitiveAgent."""

    runtime = assemble_runtime_from_graph(spec, graph, plan=plan, scope=scope)
    return CognitiveAgent(
        runtime,
        spec.profile,
        cast("BoundObservability", graph.observability),
        max_steps=spec.max_steps,
        max_wall_clock_seconds=spec.max_wall_clock_seconds,
        plan_ref=plan_ref,
    )


__all__ = ["AgentAssemblyPort", "PlanBoundAgentAssembler", "promote_lead"]
