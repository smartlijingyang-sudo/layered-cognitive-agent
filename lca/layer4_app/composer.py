"""Composition root — wires all layers into a working object graph.

``AgentComposer`` / ``TeamComposer`` assemble closed Agent / Team graphs.
No post-construction bind/install (ADR-0030).
"""

from __future__ import annotations

from typing import TypeVar

from lca.contracts.action import ActionRegistryProtocol
from lca.contracts.budget import (
    DEFAULT_MAX_STEPS,
    DEFAULT_MAX_WALL_CLOCK_SECONDS,
)
from lca.contracts.enums import (
    ActionScope,
    ComponentKind,
    DecisionGateName,
    HookEvent,
    MemoryLayer,
)
from lca.contracts.mechanisms import ComponentRegistryProtocol
from lca.contracts.protocols import (
    Body,
    Brain,
    BrainFactory,
    BudgetPolicy,
    DecisionGate,
    EventBus,
    LLMAdapter,
    MemorySystem,
    Observability,
    SharedMemoryStore,
    StateStore,
    TeamStrategy,
    TeamUnit,
    Tool,
    TransportRegistryProtocol,
)
from lca.contracts.protocols.infra import AgentTransport
from lca.contracts.protocols.orchestration import TeamContext
from lca.contracts.registries import Registries
from lca.contracts.role_team import RoleProfile, TeamConfig, ToolPermissionManifest
from lca.contracts.team_coordination import (
    Coordination,
    Graph,
    LeadMandate,
    gate_name_for_mandate,
    mandate_uses_consultation_session,
    max_rounds_from_coordination,
    strategy_key_for_coordination,
    strategy_key_for_lead,
)
from lca.layer0_infra.llm_adapter.telemetry_llm import TelemetryLLMAdapter
from lca.layer0_infra.observability.console_observability import ConsoleObservability
from lca.layer1_cognitive.body.action_catalog import build_default_action_registry
from lca.layer1_cognitive.body.safe_executor import SimpleSafeExecutor
from lca.layer1_cognitive.body.simple_body import SimpleBody
from lca.layer1_cognitive.body.tool_registry import SimpleToolRegistry
from lca.layer1_cognitive.brain.modular_brain import ModularBrain
from lca.layer1_cognitive.brain.reasoner import SimpleReasoner, SupervisorReasoner
from lca.layer1_cognitive.hook_registry import SimpleHookRegistry, default_logging_hook
from lca.layer1_cognitive.member_status import InMemoryMemberStatus
from lca.layer1_cognitive.memory.simple_memory import SimpleMemorySystem
from lca.layer1_cognitive.memory.team_shared_memory import TeamSharedMemoryStore
from lca.layer2_runtime.default_stop_rule import DefaultStopRule
from lca.layer2_runtime.event_emission import make_event_emitting_hook
from lca.layer2_runtime.outcome_policies.default_outcome_policy import DefaultStopOutcomePolicy
from lca.layer2_runtime.runtime_loop import CognitiveRuntime
from lca.layer3_agent.cognitive_agent import CognitiveAgent
from lca.layer3_agent.orchestration_registry import OrchestrationFactory
from lca.layer3_agent.orchestration_strategies.debate import DebateStrategy
from lca.layer3_agent.orchestration_strategies.graph import GraphStrategy
from lca.layer3_agent.orchestration_strategies.swarm import SwarmStrategy
from lca.layer3_agent.team_orchestrator import TeamOrchestrator
from lca.layer4_app.defaults import build_default_registries
from lca.layer4_app.team_wiring import (
    build_default_transport_registry,
    build_team_transport,
)

__all__ = [
    "AgentComposer",
    "TeamComposer",
    "build_body_from_shared",
    "build_default_transport_registry",
    "build_hooks",
    "build_team_transport",
]

T = TypeVar("T")


def _resolve_component(
    reg: ComponentRegistryProtocol,
    category: str,
    value: object,
    expected_type: type[T],
) -> T:
    result = reg.require(category, value)() if isinstance(value, str) else value
    if not isinstance(result, expected_type):
        raise TypeError(
            f"{category} expected {expected_type.__name__}, got {type(result).__name__}"
        )
    return result


def build_body_from_shared(
    tool_registry: SimpleToolRegistry,
    safe_executor: SimpleSafeExecutor,
    transport_registry: TransportRegistryProtocol,
    action_registry: ActionRegistryProtocol,
) -> Body:
    """Build Body from already-shared pipeline components.

    越界 action_type 的降级在防腐层（DecisionParser + DegradationPolicy）
    完成，Body 只做词表内分发，无需装饰器。
    """
    return SimpleBody(
        tool_registry=tool_registry,
        safe_executor=safe_executor,
        transport_registry=transport_registry,
        action_registry=action_registry,
    )


def build_hooks(observability: Observability, event_bus: EventBus) -> SimpleHookRegistry:
    hooks = SimpleHookRegistry(observability)
    event_hook = make_event_emitting_hook(event_bus)
    for event_name in HookEvent:
        hooks.register(event_name, default_logging_hook)
        hooks.register(event_name, event_hook)
    return hooks


def _promote_lead(lead: CognitiveAgent, policy: BudgetPolicy) -> CognitiveAgent:
    limits = policy.resolve(lead)
    return CognitiveAgent(
        lead.runtime,
        lead.role_profile,
        max_steps=limits.max_steps,
        max_wall_clock_seconds=limits.max_wall_clock_seconds,
    )


def _tools_from_agent(agent: CognitiveAgent) -> list[Tool]:
    runtime = agent.runtime
    body = getattr(runtime, "body", None)
    inner = getattr(body, "_inner", body)
    registry = getattr(inner, "tool_registry", None)
    if registry is None:
        return []
    entries = getattr(registry, "_entries", {})
    return list(entries.values())


def _llm_from_agent(agent: CognitiveAgent) -> LLMAdapter:
    runtime = agent.runtime
    brain = getattr(runtime, "brain", None)
    reasoner = getattr(brain, "reasoner", None)
    llm = getattr(reasoner, "llm", None)
    if llm is None:
        raise TypeError(
            "cannot recompose agent without llm on brain.reasoner; "
            "assemble via AgentComposer.compose / L4 Agent"
        )
    if isinstance(llm, TelemetryLLMAdapter):
        llm = llm._inner  # unwrap so we can re-wrap with shared obs
    # Structural check: tests may pass lightweight fakes that satisfy complete().
    if not callable(getattr(llm, "complete", None)):
        raise TypeError(f"reasoner.llm must provide complete(), got {type(llm).__name__}")
    return llm


def _obs_from_agent(agent: CognitiveAgent) -> Observability | None:
    runtime = agent.runtime
    hooks = getattr(runtime, "hooks", None)
    obs = getattr(hooks, "observability", None)
    return obs if isinstance(obs, Observability) else None


def _unwrap_llm(llm: LLMAdapter) -> LLMAdapter:
    if isinstance(llm, TelemetryLLMAdapter):
        return llm._inner
    return llm


class AgentComposer:
    """Compose a single closed CognitiveAgent."""

    def __init__(self, registries: Registries | None = None) -> None:
        self._registries = registries if registries is not None else build_default_registries()

    @property
    def registries(self) -> Registries:
        return self._registries

    def register_component(self, category: str, name: str, impl: object) -> None:
        self._registries.components.register(category, name, impl)

    def register_brain_factory(self, name: str, factory: BrainFactory) -> None:
        self._registries.brain_factories.register(name, factory)

    def register_orchestration_strategy(self, key: str, factory: OrchestrationFactory) -> None:
        self._registries.orchestration.register(key, factory)

    def compose(
        self,
        *,
        role: str,
        goal: str,
        backstory: str,
        tools: list[Tool],
        llm: LLMAdapter,
        max_steps: int = DEFAULT_MAX_STEPS,
        max_wall_clock_seconds: int | None = DEFAULT_MAX_WALL_CLOCK_SECONDS,
        memory: str | MemorySystem = "simple",
        observability: str | Observability = "console",
        state_store: str | StateStore = "memory",
        brain: str | Brain = "default",
        action_scope: ActionScope = ActionScope.SOLO,
        team_channel: AgentTransport | None = None,
        decision_gate: DecisionGate | None = None,
        lead_cognition: bool = False,
        shared_store: SharedMemoryStore | None = None,
    ) -> CognitiveAgent:
        """Assemble a complete CognitiveAgent (closed graph)."""
        reg = self._registries.components

        permission_manifest = ToolPermissionManifest(allowed_tools=[t.name for t in tools])
        role_profile = RoleProfile(
            role=role,
            goal=goal,
            backstory=backstory,
            tool_permission_manifest=permission_manifest,
        )

        obs = _resolve_component(reg, ComponentKind.OBSERVABILITY, observability, Observability)  # type: ignore[type-abstract]
        if shared_store is not None:
            mem: MemorySystem = SimpleMemorySystem(shared_store=shared_store)
        elif isinstance(memory, str):
            mem = _resolve_component(reg, ComponentKind.MEMORY, memory, MemorySystem)  # type: ignore[type-abstract]
        else:
            mem = memory
        ss = _resolve_component(reg, ComponentKind.STATE_STORE, state_store, StateStore)  # type: ignore[type-abstract]

        tool_registry = SimpleToolRegistry()
        for t in tools:
            tool_registry.register(t)
        safe_executor = SimpleSafeExecutor(permission_manifest, obs)
        transport_registry = build_default_transport_registry()
        if team_channel is not None:
            transport_registry.register(team_channel)

        action_registry = build_default_action_registry(
            tool_registry,
            safe_executor,
            transport_registry,
            scope=action_scope,
        )

        instrumented_llm: LLMAdapter = TelemetryLLMAdapter(_unwrap_llm(llm))

        resolved_brain: Brain
        if isinstance(brain, str):
            factory_reg = self._registries.brain_factories
            if brain not in factory_reg:
                raise ValueError(f"Unknown brain: {brain!r}. Available: {factory_reg.list()}")
            tools_desc = ", ".join(t.name for t in tools) or "(no tools available)"
            factory = factory_reg.resolve(brain)
            resolved_brain = factory(
                instrumented_llm,
                role_profile,
                tools_desc,
                action_registry=action_registry,
                tools=tools,
            )
        else:
            resolved_brain = brain

        if lead_cognition or decision_gate is not None:
            resolved_brain = self._apply_lead_brain(
                resolved_brain,
                lead_cognition=lead_cognition,
                decision_gate=decision_gate,
            )

        body = build_body_from_shared(
            tool_registry,
            safe_executor,
            transport_registry,
            action_registry,
        )
        event_bus = _resolve_component(reg, ComponentKind.EVENT_BUS, "simple", EventBus)  # type: ignore[type-abstract]
        hooks = build_hooks(obs, event_bus)
        runtime = CognitiveRuntime(
            resolved_brain,
            body,
            mem,
            hooks,
            ss,
            stop_rule=DefaultStopRule(outcome_policy=DefaultStopOutcomePolicy()),
        )
        return CognitiveAgent(
            runtime,
            role_profile,
            max_steps=max_steps,
            max_wall_clock_seconds=max_wall_clock_seconds,
        )

    @staticmethod
    def _apply_lead_brain(
        brain: Brain,
        *,
        lead_cognition: bool,
        decision_gate: DecisionGate | None,
    ) -> Brain:
        """Return a new ModularBrain with lead reasoner/gate when applicable."""
        if not isinstance(brain, ModularBrain):
            if decision_gate is not None or lead_cognition:
                raise TypeError(
                    f"lead composition requires ModularBrain (got {type(brain).__name__})"
                )
            return brain

        reasoner = brain.reasoner
        if lead_cognition:
            if isinstance(reasoner, SupervisorReasoner):
                pass
            elif isinstance(reasoner, SimpleReasoner):
                reasoner = SupervisorReasoner.from_simple(reasoner)
            else:
                raise TypeError(
                    f"cannot promote reasoner type {type(reasoner).__name__} to SupervisorReasoner"
                )

        return ModularBrain(
            reasoner=reasoner,
            decision_parser=brain.decision_parser,
            critic=brain.critic,
            evaluation_pipeline=brain.evaluation_pipeline,
            skill_router=brain.skill_router,
            decision_gate=decision_gate,
        )

    def compose_as_lead(
        self,
        raw: CognitiveAgent,
        *,
        transport: AgentTransport,
        mandate: LeadMandate,
        observability: Observability | None = None,
    ) -> CognitiveAgent:
        """Build a new closed lead agent from a raw agent (no patch)."""
        tools = _tools_from_agent(raw)
        llm = _llm_from_agent(raw)
        profile = raw.role_profile
        gate = self._resolve_decision_gate(gate_name_for_mandate(mandate))
        obs_arg: str | Observability = observability if observability is not None else "console"
        composed = self.compose(
            role=profile.role,
            goal=profile.goal,
            backstory=profile.backstory,
            tools=tools,
            llm=llm,
            max_steps=raw.max_steps,
            max_wall_clock_seconds=raw.max_wall_clock_seconds,
            action_scope=ActionScope.LEAD,
            team_channel=transport,
            decision_gate=gate,
            lead_cognition=True,
            observability=obs_arg,
        )
        policy = _resolve_component(
            self._registries.components,
            ComponentKind.BUDGET_POLICY,
            "lead",
            BudgetPolicy,  # type: ignore[type-abstract]
        )
        return _promote_lead(composed, policy)

    def compose_member(
        self,
        raw: CognitiveAgent,
        *,
        shared_store: SharedMemoryStore | None = None,
        observability: Observability | None = None,
    ) -> CognitiveAgent:
        """Rebuild member with optional shared memory / shared observability."""
        if shared_store is None and observability is None:
            return raw
        tools = _tools_from_agent(raw)
        llm = _llm_from_agent(raw)
        profile = raw.role_profile
        obs_arg: str | Observability = observability if observability is not None else "console"
        return self.compose(
            role=profile.role,
            goal=profile.goal,
            backstory=profile.backstory,
            tools=tools,
            llm=llm,
            max_steps=raw.max_steps,
            max_wall_clock_seconds=raw.max_wall_clock_seconds,
            action_scope=ActionScope.MEMBER,
            shared_store=shared_store,
            observability=obs_arg,
        )

    def _resolve_decision_gate(self, name: DecisionGateName) -> DecisionGate | None:
        if name == DecisionGateName.NONE:
            return None
        factory = self._registries.components.require(ComponentKind.DECISION_GATE, name)
        result = factory()
        if not isinstance(result, DecisionGate):
            raise TypeError(
                f"decision_gate factory produced {type(result).__name__}, expected DecisionGate"
            )
        return result


class TeamComposer(AgentComposer):
    """Compose a closed team: members + (lead XOR coordination)."""

    def compose_team(
        self,
        *,
        members: list[CognitiveAgent],
        lead: tuple[CognitiveAgent, LeadMandate] | None = None,
        coordination: Coordination | None = None,
        shared_memory_layers: list[MemoryLayer] | None = None,
        strategy: TeamStrategy | None = None,
        delegate_max_attempts: int | None = None,
        observability: Observability | None = None,
    ) -> TeamUnit:
        if (lead is None) == (coordination is None):
            raise ValueError("Team requires exactly one of lead= or coordination=")

        if lead is not None:
            raw_lead, mandate = lead
            strategy_key = strategy_key_for_lead()
            max_rounds = None
        else:
            if coordination is None:  # pragma: no cover - guarded above
                raise ValueError("Team requires exactly one of lead= or coordination=")
            strategy_key = strategy_key_for_coordination(coordination)
            max_rounds = max_rounds_from_coordination(coordination)
            mandate = None
            raw_lead = None

        config = TeamConfig(
            strategy_key=strategy_key,
            max_rounds=max_rounds,
            shared_memory_layers=list(shared_memory_layers or []),
            lead_mandate=mandate,
        )
        if delegate_max_attempts is not None:
            config.delegate_max_attempts = delegate_max_attempts

        shared_store: SharedMemoryStore | None = None
        if config.shared_memory_layers:
            shared_store = TeamSharedMemoryStore(config.shared_memory_layers)

        # One shared Observability for orchestrator + all members (span tree continuity).
        shared_obs = observability
        if shared_obs is None and members:
            shared_obs = _obs_from_agent(members[0])
        if shared_obs is None and raw_lead is not None:
            shared_obs = _obs_from_agent(raw_lead)
        if shared_obs is None:
            shared_obs = ConsoleObservability()

        composed_members = [
            self.compose_member(m, shared_store=shared_store, observability=shared_obs)
            for m in members
        ]

        resolved_strategy = strategy
        if resolved_strategy is None and isinstance(coordination, Graph):
            resolved_strategy = GraphStrategy(execution_graph=coordination.execution_graph)
        if resolved_strategy is None and coordination is not None:
            key = strategy_key_for_coordination(coordination)
            if key == "peer_swarm":
                rounds = max_rounds_from_coordination(coordination)
                resolved_strategy = SwarmStrategy(max_rounds=rounds)
            elif key == "debate":
                rounds = max_rounds_from_coordination(coordination)
                resolved_strategy = DebateStrategy(max_rounds=rounds)
            else:
                resolved_strategy = self._registries.orchestration.resolve(key)
        if resolved_strategy is None and lead is not None:
            resolved_strategy = self._registries.orchestration.resolve(strategy_key_for_lead())
        if resolved_strategy is None:
            raise ValueError(f"unable to resolve TeamStrategy for key={strategy_key!r}")

        transport = build_team_transport(composed_members)
        teammate_profiles = [m.role_profile for m in composed_members]

        closed_lead: CognitiveAgent | None = None
        member_status = None
        if raw_lead is not None and mandate is not None:
            closed_lead = self.compose_as_lead(
                raw_lead,
                transport=transport,
                mandate=mandate,
                observability=shared_obs,
            )
            if mandate_uses_consultation_session(mandate):
                role_order = tuple(m.role_profile.role for m in composed_members)
                member_status = InMemoryMemberStatus(role_order=role_order)

        context = TeamContext(
            members=composed_members,
            config=config,
            lead=closed_lead,
            transport=transport,
            teammates=teammate_profiles,
            member_status=member_status,
            team_id=f"team-{strategy_key}",
            shared_memory=shared_store,
            observability=shared_obs,
        )
        return TeamOrchestrator(context, resolved_strategy)
