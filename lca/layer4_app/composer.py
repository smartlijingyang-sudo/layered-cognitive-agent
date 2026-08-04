"""Composition root — wires all layers into working object graphs.

``AgentComposer`` / ``TeamComposer`` 从声明式 ``AgentSpec`` / ``LeadSpec``
组装封闭的 Agent / Team 对象图：spec 是唯一声明式输入，composer 是唯一
组装点，构造后无 bind/install（ADR-0005 / ADR-0029 / ADR-0030 / ADR-0033）。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import TypeVar

from lca.contracts.action import ActionRegistryProtocol
from lca.contracts.agent_spec import OBSERVABILITY_CHOICE_CONSOLE, AgentSpec, LeadSpec
from lca.contracts.enums import (
    ActionScope,
    ComponentKind,
    DecisionGateName,
    HookEvent,
    MemoryLayer,
)
from lca.contracts.mechanisms import ComponentRegistryProtocol
from lca.contracts.protocols import (
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
)
from lca.contracts.protocols.infra import AgentTransport
from lca.contracts.protocols.orchestration import TeamContext
from lca.contracts.registries import Registries
from lca.contracts.role_team import RoleProfile, TeamConfig
from lca.contracts.team_coordination import (
    Coordination,
    LeadMandate,
    gate_name_for_mandate,
    mandate_uses_consultation_session,
    max_rounds_from_coordination,
    strategy_key_for_coordination,
    strategy_key_for_lead,
)
from lca.layer0_infra.llm_adapter.telemetry_llm import TelemetryLLMAdapter
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
from lca.layer3_agent.team_orchestrator import TeamOrchestrator
from lca.layer4_app.defaults import EVENT_BUS_SIMPLE, build_default_registries
from lca.layer4_app.policies import LEAD_BUDGET_POLICY_KEY
from lca.layer4_app.team_wiring import (
    build_default_transport_registry,
    build_team_transport,
)

__all__ = [
    "AgentComposer",
    "TeamComposer",
    "build_default_transport_registry",
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


def _unwrap_llm(llm: LLMAdapter) -> LLMAdapter:
    if isinstance(llm, TelemetryLLMAdapter):
        return llm._inner
    return llm


def _promote_lead(lead: CognitiveAgent, policy: BudgetPolicy) -> CognitiveAgent:
    limits = policy.resolve(lead)
    return CognitiveAgent(
        lead.runtime,
        lead.role_profile,
        max_steps=limits.max_steps,
        max_wall_clock_seconds=limits.max_wall_clock_seconds,
    )


class AgentComposer:
    """Compose a single closed CognitiveAgent from a declarative AgentSpec."""

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
        spec: AgentSpec,
        *,
        action_scope: ActionScope = ActionScope.SOLO,
        team_channel: AgentTransport | None = None,
        decision_gate: DecisionGate | None = None,
        lead_cognition: bool = False,
        shared_store: SharedMemoryStore | None = None,
    ) -> CognitiveAgent:
        """Assemble a complete CognitiveAgent from *spec* (closed graph)."""
        profile = spec.profile
        obs = self._resolve_observability(spec.observability)
        mem = self._resolve_memory(spec.memory, shared_store)
        state_store = _resolve_component(
            self._registries.components,
            ComponentKind.STATE_STORE,
            spec.state_store,
            StateStore,  # type: ignore[type-abstract]
        )

        tool_registry = SimpleToolRegistry()
        for tool in spec.tools:
            tool_registry.register(tool)
        safe_executor = SimpleSafeExecutor(profile.tool_permission_manifest, obs)
        transport_registry = build_default_transport_registry()
        if team_channel is not None:
            transport_registry.register(team_channel)
        action_registry = build_default_action_registry(
            tool_registry,
            safe_executor,
            transport_registry,
            scope=action_scope,
        )

        brain = self._resolve_brain(spec, profile, action_registry)
        if lead_cognition or decision_gate is not None:
            brain = self._apply_lead_brain(
                brain,
                lead_cognition=lead_cognition,
                decision_gate=decision_gate,
            )

        body = SimpleBody(
            tool_registry=tool_registry,
            safe_executor=safe_executor,
            transport_registry=transport_registry,
            action_registry=action_registry,
        )
        event_bus = _resolve_component(
            self._registries.components,
            ComponentKind.EVENT_BUS,
            EVENT_BUS_SIMPLE,
            EventBus,  # type: ignore[type-abstract]
        )
        runtime = CognitiveRuntime(
            brain,
            body,
            mem,
            self._build_hooks(obs, event_bus),
            state_store,
            stop_rule=DefaultStopRule(outcome_policy=DefaultStopOutcomePolicy()),
        )
        return CognitiveAgent(
            runtime,
            profile,
            max_steps=spec.max_steps,
            max_wall_clock_seconds=spec.max_wall_clock_seconds,
        )

    def compose_as_lead(
        self,
        spec: AgentSpec,
        *,
        transport: AgentTransport,
        mandate: LeadMandate,
        observability: Observability | None = None,
    ) -> CognitiveAgent:
        """Build a closed lead agent from *spec* (supervisor cognition + gate)."""
        lead_spec = (
            replace(spec, observability=observability) if observability is not None else spec
        )
        gate = self._resolve_decision_gate(gate_name_for_mandate(mandate))
        composed = self.compose(
            lead_spec,
            action_scope=ActionScope.LEAD,
            team_channel=transport,
            decision_gate=gate,
            lead_cognition=True,
        )
        policy = _resolve_component(
            self._registries.components,
            ComponentKind.BUDGET_POLICY,
            LEAD_BUDGET_POLICY_KEY,
            BudgetPolicy,  # type: ignore[type-abstract]
        )
        return _promote_lead(composed, policy)

    def compose_member(
        self,
        spec: AgentSpec,
        *,
        shared_store: SharedMemoryStore | None = None,
        observability: Observability | None = None,
    ) -> CognitiveAgent:
        """Build a team member from *spec* (shared memory / shared observability)."""
        member_spec = (
            replace(spec, observability=observability) if observability is not None else spec
        )
        return self.compose(member_spec, action_scope=ActionScope.MEMBER, shared_store=shared_store)

    def _resolve_observability(self, choice: str | Observability) -> Observability:
        return _resolve_component(
            self._registries.components,
            ComponentKind.OBSERVABILITY,
            choice,
            Observability,  # type: ignore[type-abstract]
        )

    def _resolve_memory(
        self,
        choice: str | MemorySystem,
        shared_store: SharedMemoryStore | None,
    ) -> MemorySystem:
        if shared_store is not None:
            return SimpleMemorySystem(shared_store=shared_store)
        return _resolve_component(
            self._registries.components,
            ComponentKind.MEMORY,
            choice,
            MemorySystem,  # type: ignore[type-abstract]
        )

    def _resolve_brain(
        self,
        spec: AgentSpec,
        profile: RoleProfile,
        action_registry: ActionRegistryProtocol,
    ) -> Brain:
        if not isinstance(spec.brain, str):
            return spec.brain
        factory_reg = self._registries.brain_factories
        if spec.brain not in factory_reg:
            raise ValueError(f"Unknown brain: {spec.brain!r}. Available: {factory_reg.list()}")
        tools_desc = ", ".join(t.name for t in spec.tools) or "(no tools available)"
        factory = factory_reg.resolve(spec.brain)
        instrumented_llm: LLMAdapter = TelemetryLLMAdapter(_unwrap_llm(spec.llm))
        resolved: Brain = factory(
            instrumented_llm,
            profile,
            tools_desc,
            action_registry=action_registry,
            tools=list(spec.tools),
        )
        return resolved

    @staticmethod
    def _build_hooks(observability: Observability, event_bus: EventBus) -> SimpleHookRegistry:
        hooks = SimpleHookRegistry(observability)
        event_hook = make_event_emitting_hook(event_bus)
        for event_name in HookEvent:
            hooks.register(event_name, default_logging_hook)
            hooks.register(event_name, event_hook)
        return hooks

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
    """Compose a closed team from declarative specs: members + (lead XOR coordination)."""

    def compose_team(
        self,
        *,
        members: Sequence[AgentSpec],
        lead: LeadSpec | None = None,
        coordination: Coordination | None = None,
        shared_memory_layers: Sequence[MemoryLayer] | None = None,
        strategy: TeamStrategy | None = None,
        delegate_max_attempts: int | None = None,
        observability: str | Observability | None = None,
    ) -> TeamUnit:
        if (lead is None) == (coordination is None):
            raise ValueError("Team requires exactly one of lead= or coordination=")

        if lead is not None:
            strategy_key = strategy_key_for_lead()
            max_rounds = None
            mandate: LeadMandate | None = lead.mandate
        else:
            if coordination is None:  # pragma: no cover - guarded above
                raise ValueError("Team requires exactly one of lead= or coordination=")
            strategy_key = strategy_key_for_coordination(coordination)
            max_rounds = max_rounds_from_coordination(coordination)
            mandate = None

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
        shared_obs = self._resolve_shared_observability(observability, members, lead)
        composed_members = [
            self.compose_member(m, shared_store=shared_store, observability=shared_obs)
            for m in members
        ]

        resolved_strategy: TeamStrategy = (
            strategy
            if strategy is not None
            else self._registries.orchestration.resolve(strategy_key, coordination)
        )

        transport = build_team_transport(composed_members)
        closed_lead: CognitiveAgent | None = None
        member_status = None
        if lead is not None:
            closed_lead = self.compose_as_lead(
                lead.agent,
                transport=transport,
                mandate=lead.mandate,
                observability=shared_obs,
            )
            if mandate_uses_consultation_session(lead.mandate):
                role_order = tuple(m.role_profile.role for m in composed_members)
                member_status = InMemoryMemberStatus(role_order=role_order)

        context = TeamContext(
            members=composed_members,
            config=config,
            lead=closed_lead,
            transport=transport,
            teammates=[m.role_profile for m in composed_members],
            member_status=member_status,
            team_id=f"team-{strategy_key}",
            shared_memory=shared_store,
            observability=shared_obs,
        )
        return TeamOrchestrator(context, resolved_strategy)

    def _resolve_shared_observability(
        self,
        explicit: str | Observability | None,
        members: Sequence[AgentSpec],
        lead: LeadSpec | None,
    ) -> Observability:
        """Single shared Observability instance for the whole team.

        Priority: explicit arg > member specs in order > lead spec > console default.
        First instance wins as-is; first registry name is resolved once and shared.
        """
        candidates: list[str | Observability] = []
        if explicit is not None:
            candidates.append(explicit)
        candidates.extend(member.observability for member in members)
        if lead is not None:
            candidates.append(lead.agent.observability)
        for choice in candidates:
            if isinstance(choice, Observability):
                return choice
            if isinstance(choice, str):
                return self._resolve_observability(choice)
        return self._resolve_observability(OBSERVABILITY_CHOICE_CONSOLE)
