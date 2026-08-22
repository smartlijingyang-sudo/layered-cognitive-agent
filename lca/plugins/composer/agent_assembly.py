"""Plan-bound Agent assembly used by the TeamComposer recursion seam."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Protocol

from lca.contracts.atoms.enums import ActionScope, ComponentKind
from lca.contracts.mechanisms import consume
from lca.contracts.mechanisms.capability import MissingCapabilityError, require_capability
from lca.contracts.models.team.team_coordination import LeadMandate, gate_name_for_mandate
from lca.contracts.protocols import BudgetPolicy, SharedMemoryStore
from lca.contracts.protocols.infra import AgentTransport
from lca.contracts.protocols.spec import AgentSpec
from lca.layer0_infra.observability import BoundObservability
from lca.layer2_runtime.runtime_loop import CognitiveRuntime
from lca.layer3_agent.cognitive_agent import CognitiveAgent
from lca.plugins.composer.plan_binding import bind_plan
from lca.plugins.composer.plan_composition_support import (
    AgentCompositionRequest,
    resolve_decision_gate,
)
from lca.plugins.composer.runtime_factory import RuntimeDeps, build_cognitive_runtime

if TYPE_CHECKING:
    from cordis import Context

    from lca.contracts.harness.composer import AgentGraph
    from lca.contracts.protocols import DecisionGate
    from lca.contracts.protocols.plan import CompiledRunPlan


_LEAD_BUDGET_POLICY_KEY = "lead"


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


class PlanBoundAgentAssembler:
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
        """Compile the profile plan, bind the graph, and close one Agent."""

        plan = _compiled_plan_from_scope(scope)
        request = AgentCompositionRequest(
            spec=spec,
            action_scope=action_scope,
            team_channel=team_channel,
            decision_gate=decision_gate,
            shared_store=shared_store,
        )
        bound = bind_plan(request, plan, scope=scope)
        return _agent_from_bound_graph(spec, bound.graph, plan=bound.plan, plan_ref=bound.plan_ref)

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
        components = require_capability(scope, "component_registry")
        policy = components.require(ComponentKind.BUDGET_POLICY, _LEAD_BUDGET_POLICY_KEY)()
        if not isinstance(policy, BudgetPolicy):
            raise TypeError(f"lead budget policy must be BudgetPolicy, got {type(policy).__name__}")
        return promote_lead(lead, policy)


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


def _compiled_plan_from_scope(scope: Context) -> CompiledRunPlan:
    """Compile the resolved boot Profile into the only runnable input plan."""

    resolved = getattr(scope, "resolved_profile", None)
    if resolved is None:
        raise MissingCapabilityError("resolved_profile")
    from lca.harness.profile.plan_compiler import compile_plan

    return compile_plan(resolved)


def _agent_from_bound_graph(
    spec: AgentSpec,
    graph: AgentGraph,
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


__all__ = ["AgentAssemblyPort", "PlanBoundAgentAssembler", "promote_lead"]
