"""Plan-bound sub-composers for AgentGraph and TeamGraph."""

from __future__ import annotations

from typing import TYPE_CHECKING

from lca.contracts.capabilities import BODIES, HOOKS, MEMORY, STATE_STORE, STOP_RULES, STRATEGIES
from lca.contracts.harness.composer import AgentGraph, TeamGraph
from lca.contracts.mechanisms.capability import require_capability
from lca.contracts.protocols import TeamAssembly, TeamStage
from lca.contracts.protocols.spec import LeadSpec, TeamSpec, strategy_key_for_governance
from lca.layer1_cognitive.body.action_catalog import build_default_action_registry
from lca.layer1_cognitive.memory.team_shared_memory import TeamSharedMemoryStore
from lca.layer3_agent.member_invoke import TransportMemberInvoker
from lca.layer4_app.team_wiring import build_team_transport
from lca.plugins.composer.plan_composition_support import (
    AgentCompositionRequest,
    apply_lead_brain,
    build_perceive_hub,
    fork_transport,
    instrument_llm,
    require_factory,
    resolve_brain,
    resolve_memory,
    resolve_observability,
    resolve_state_store,
    resolve_team_observability,
)

if TYPE_CHECKING:
    from cordis import Context


class BrainComposer:
    """Compose the think cluster of a plan-bound AgentGraph."""

    key = "brain"

    def compose_agent(self, request: AgentCompositionRequest, scope: Context) -> AgentGraph:
        llm = instrument_llm(request.spec.llm)
        brain = resolve_brain(request.spec, llm, scope=scope)
        if request.decision_gate is not None:
            brain = apply_lead_brain(brain, request.decision_gate)
        return AgentGraph(
            brain=brain,
            body=None,
            memory=None,
            state_store=None,
            perceive_hub=None,
            hooks=None,
            observability=None,
            llm=llm,
            stop_rule=None,
            metadata={"composer": self.key},
        )

    def compose_team(self, spec: TeamSpec, scope: Context) -> TeamGraph:
        del spec, scope
        raise TypeError("BrainComposer cannot compose a TeamGraph")


class BodyComposer:
    """Compose the act cluster of a plan-bound AgentGraph."""

    key = "body"

    def compose_agent(self, request: AgentCompositionRequest, scope: Context) -> AgentGraph:
        tools = require_factory(scope, "tools.compose_service")()
        for tool in request.spec.tools:
            tools.register(tool)
        safe_executor = require_factory(scope, "safe_executor.simple")(
            request.spec.profile.tool_permission_manifest
        )
        transport = fork_transport(
            require_capability(scope, "transport"), request.team_channel, scope
        )
        registry = build_default_action_registry(
            tools, safe_executor, transport, scope=request.action_scope
        )
        body = require_capability(scope, BODIES.key).create(
            "simple",
            tool_registry=tools,
            safe_executor=safe_executor,
            transport_registry=transport,
            action_registry=registry,
        )
        return AgentGraph(
            brain=None,
            body=body,
            memory=None,
            state_store=None,
            perceive_hub=None,
            hooks=require_capability(scope, HOOKS.key).create("simple"),
            observability=None,
            llm=None,
            stop_rule=None,
            metadata={"composer": self.key},
        )

    def compose_team(self, spec: TeamSpec, scope: Context) -> TeamGraph:
        del spec, scope
        raise TypeError("BodyComposer cannot compose a TeamGraph")


class PerceiveComposer:
    """Compose the perceive, memory, state and stop clusters of an AgentGraph."""

    key = "perceive"

    def compose_agent(self, request: AgentCompositionRequest, scope: Context) -> AgentGraph:
        observability = resolve_observability(request.spec, scope)
        memory = resolve_memory(
            request.spec.memory, request.shared_store, require_capability(scope, MEMORY.key)
        )
        state_store = resolve_state_store(
            request.spec.state_store, require_capability(scope, STATE_STORE.key)
        )
        return AgentGraph(
            brain=None,
            body=None,
            memory=memory,
            state_store=state_store,
            perceive_hub=build_perceive_hub(
                memory, hub=observability, scope=scope, action_scope=request.action_scope
            ),
            hooks=None,
            observability=observability,
            llm=None,
            stop_rule=require_capability(scope, STOP_RULES.key).create("default"),
            metadata={"composer": self.key},
        )

    def compose_team(self, spec: TeamSpec, scope: Context) -> TeamGraph:
        del spec, scope
        raise TypeError("PerceiveComposer cannot compose a TeamGraph")


class TeamComposer:
    """Compose the collaboration cluster through recursively plan-bound Agents."""

    key = "team"

    def compose_agent(self, request: AgentCompositionRequest, scope: Context) -> AgentGraph:
        del request, scope
        raise TypeError("TeamComposer cannot compose an AgentGraph")

    def compose_team(self, spec: TeamSpec, scope: Context) -> TeamGraph:
        from lca.layer4_app.spawn import spawn_lead, spawn_member

        observability = resolve_team_observability(spec, scope)
        shared_store = (
            TeamSharedMemoryStore(list(spec.shared_memory_layers))
            if spec.shared_memory_layers
            else None
        )
        members = tuple(
            spawn_member(
                member, shared_store=shared_store, observability=observability, scope=scope
            )
            for member in spec.members
        )
        roles = [member.role_profile.role for member in members]
        if any(not role for role in roles) or len(set(roles)) != len(roles):
            raise ValueError("team member roles must be non-empty and unique")
        transport = build_team_transport(list(members))
        stage = TeamStage(members=members, invoker=TransportMemberInvoker(transport))
        lead = (
            spawn_lead(
                spec.governance.agent,
                transport=transport,
                mandate=spec.governance.mandate,
                observability=observability,
                scope=scope,
            )
            if isinstance(spec.governance, LeadSpec)
            else None
        )
        assembly = TeamAssembly(
            governance=spec.governance,
            stage=stage,
            lead=lead,
            delegate_max_attempts=spec.delegate_max_attempts,
        )
        return TeamGraph(
            members=members,
            strategy=require_capability(scope, STRATEGIES.key).create(
                strategy_key_for_governance(spec.governance), assembly
            ),
            stage=stage,
            transport=transport,
            observability=observability,
            metadata={"composer": self.key, "lead": lead},
        )


__all__ = ["BodyComposer", "BrainComposer", "PerceiveComposer", "TeamComposer"]
