"""Composition root — wires all layers into a working object graph.

Sole module that assembles Agent / Team object graphs via ``Assembly``.
Closed object graph (ADR-0029): no post-construction bind/install.
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
    TeamProcess,
)
from lca.contracts.graph import ExecutionGraph
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
    TeamProcessStrategy,
    TeamUnit,
    Tool,
    TransportRegistryProtocol,
)
from lca.contracts.protocols.infra import AgentTransport
from lca.contracts.protocols.orchestration import TeamContext
from lca.contracts.registries import Registries
from lca.contracts.role_team import RoleProfile, TeamConfig, ToolPermissionManifest
from lca.contracts.supervisor_mode import (
    SupervisorMode,
    decision_gate_name_for_mode,
    mode_uses_consultation_session,
)
from lca.layer1_cognitive.body.action_catalog import build_default_action_registry
from lca.layer1_cognitive.body.fallback_decorated_body import FallbackDecoratedBody
from lca.layer1_cognitive.body.fallback_policy import FallbackActionPolicy
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
from lca.layer3_agent.orchestration_strategies.graph import GraphStrategy
from lca.layer3_agent.team_orchestrator import TeamOrchestrator
from lca.layer4_app.defaults import build_default_registries
from lca.layer4_app.team_wiring import (
    build_default_transport_registry,
    build_team_transport,
)

__all__ = [
    "Assembly",
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
    *,
    enable_fallback: bool = True,
) -> Body:
    """Build Body from already-shared pipeline components."""
    simple_body = SimpleBody(
        tool_registry=tool_registry,
        safe_executor=safe_executor,
        transport_registry=transport_registry,
        action_registry=action_registry,
    )
    if enable_fallback:
        return FallbackDecoratedBody(
            inner=simple_body,
            fallback_handler=FallbackActionPolicy(),
            action_registry=action_registry,
        )
    return simple_body


def build_hooks(observability: Observability, event_bus: EventBus) -> SimpleHookRegistry:
    hooks = SimpleHookRegistry(observability)
    event_hook = make_event_emitting_hook(event_bus)
    for event_name in HookEvent:
        hooks.register(event_name, default_logging_hook)
        hooks.register(event_name, event_hook)
    return hooks


def _promote_supervisor(supervisor: CognitiveAgent, policy: BudgetPolicy) -> CognitiveAgent:
    limits = policy.resolve(supervisor)
    return CognitiveAgent(
        supervisor.runtime,
        supervisor.role_profile,
        max_steps=limits.max_steps,
        max_wall_clock_seconds=limits.max_wall_clock_seconds,
    )


def _tools_from_agent(agent: CognitiveAgent) -> list[Tool]:
    runtime = agent.runtime
    body = getattr(runtime, "body", None)
    # Unwrap fallback decorator
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
            "assemble via Assembly.assemble_agent / L4 Agent"
        )
    if not isinstance(llm, LLMAdapter):
        raise TypeError(f"reasoner.llm must be LLMAdapter, got {type(llm).__name__}")
    return llm


class Assembly:
    """组合根（ADR-0024 / ADR-0029）。私有 Registries，封闭对象图。"""

    def __init__(self, registries: Registries | None = None) -> None:
        self._registries = registries if registries is not None else build_default_registries()

    @property
    def registries(self) -> Registries:
        return self._registries

    def register_component(self, category: str, name: str, impl: object) -> None:
        self._registries.components.register(category, name, impl)

    def register_brain_factory(self, name: str, factory: BrainFactory) -> None:
        self._registries.brain_factories.register(name, factory)

    def register_orchestration_strategy(
        self, process: TeamProcess, factory: OrchestrationFactory
    ) -> None:
        self._registries.orchestration.register(process, factory)

    def assemble_agent(
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
        supervisor_cognition: bool = False,
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

        resolved_brain: Brain
        if isinstance(brain, str):
            factory_reg = self._registries.brain_factories
            if brain not in factory_reg:
                raise ValueError(f"Unknown brain: {brain!r}. Available: {factory_reg.list()}")
            tools_desc = ", ".join(t.name for t in tools) or "(no tools available)"
            factory = factory_reg.resolve(brain)
            resolved_brain = factory(
                llm, role_profile, tools_desc, action_registry=action_registry, tools=tools
            )
        else:
            resolved_brain = brain

        if supervisor_cognition or decision_gate is not None:
            resolved_brain = self._apply_supervisor_brain(
                resolved_brain,
                supervisor_cognition=supervisor_cognition,
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
    def _apply_supervisor_brain(
        brain: Brain,
        *,
        supervisor_cognition: bool,
        decision_gate: DecisionGate | None,
    ) -> Brain:
        """Return a new ModularBrain with supervisor reasoner/gate when applicable."""
        if not isinstance(brain, ModularBrain):
            if decision_gate is not None or supervisor_cognition:
                raise TypeError(
                    f"supervisor composition requires ModularBrain (got {type(brain).__name__})"
                )
            return brain

        reasoner = brain.reasoner
        if supervisor_cognition:
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

    def recompose_as_supervisor(
        self,
        raw: CognitiveAgent,
        *,
        transport: AgentTransport,
        mode: SupervisorMode,
    ) -> CognitiveAgent:
        """Build a new closed supervisor agent from a raw agent (no patch)."""
        tools = _tools_from_agent(raw)
        llm = _llm_from_agent(raw)
        profile = raw.role_profile
        gate = self._resolve_decision_gate(decision_gate_name_for_mode(mode))
        composed = self.assemble_agent(
            role=profile.role,
            goal=profile.goal,
            backstory=profile.backstory,
            tools=tools,
            llm=llm,
            max_steps=raw.max_steps,
            max_wall_clock_seconds=raw.max_wall_clock_seconds,
            action_scope=ActionScope.SUPERVISOR,
            team_channel=transport,
            decision_gate=gate,
            supervisor_cognition=True,
        )
        policy = _resolve_component(
            self._registries.components,
            ComponentKind.BUDGET_POLICY,
            "supervisor",
            BudgetPolicy,  # type: ignore[type-abstract]
        )
        return _promote_supervisor(composed, policy)

    def recompose_member(
        self,
        raw: CognitiveAgent,
        *,
        shared_store: SharedMemoryStore | None = None,
    ) -> CognitiveAgent:
        """Rebuild member with optional shared memory (closed graph)."""
        if shared_store is None:
            return raw
        tools = _tools_from_agent(raw)
        llm = _llm_from_agent(raw)
        profile = raw.role_profile
        return self.assemble_agent(
            role=profile.role,
            goal=profile.goal,
            backstory=profile.backstory,
            tools=tools,
            llm=llm,
            max_steps=raw.max_steps,
            max_wall_clock_seconds=raw.max_wall_clock_seconds,
            action_scope=ActionScope.MEMBER,
            shared_store=shared_store,
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

    def assemble_team(
        self,
        *,
        members: list[CognitiveAgent],
        process: TeamProcess | None = None,
        supervisor: CognitiveAgent | None = None,
        max_rounds: int | None = None,
        shared_memory_layers: list[MemoryLayer] | None = None,
        execution_graph: ExecutionGraph | None = None,
        strategy: TeamProcessStrategy | None = None,
        supervisor_mode: SupervisorMode | None = None,
        delegate_max_attempts: int | None = None,
    ) -> TeamUnit:
        """Assemble a closed team graph. Hierarchical requires supervisor_mode."""
        process_val = process if process is not None else TeamProcess.HIERARCHICAL
        mode = supervisor_mode
        if process_val is TeamProcess.HIERARCHICAL and mode is None:
            mode = SupervisorMode.CONSULTATION

        config = TeamConfig(
            process=process_val,
            max_rounds=max_rounds,
            shared_memory_layers=list(shared_memory_layers or []),
            supervisor_mode=mode if process_val is TeamProcess.HIERARCHICAL else None,
        )
        if delegate_max_attempts is not None:
            config.delegate_max_attempts = delegate_max_attempts

        shared_store: SharedMemoryStore | None = None
        if config.shared_memory_layers:
            shared_store = TeamSharedMemoryStore(config.shared_memory_layers)

        composed_members = [self.recompose_member(m, shared_store=shared_store) for m in members]

        resolved_strategy = strategy
        if resolved_strategy is None and process_val is TeamProcess.GRAPH:
            if execution_graph is None:
                raise ValueError(
                    "process=GRAPH requires execution_graph= (or pass strategy=GraphStrategy(...))"
                )
            resolved_strategy = GraphStrategy(execution_graph=execution_graph)
        if resolved_strategy is None:
            resolved_strategy = self._registries.orchestration.resolve(process_val)

        transport = build_team_transport(composed_members)
        teammate_profiles = [m.role_profile for m in composed_members]

        closed_supervisor: CognitiveAgent | None = None
        member_status = None
        if supervisor is not None:
            if mode is None:
                raise ValueError("supervisor provided but supervisor_mode is None")
            closed_supervisor = self.recompose_as_supervisor(
                supervisor, transport=transport, mode=mode
            )
            if mode_uses_consultation_session(mode):
                role_order = tuple(m.role_profile.role for m in composed_members)
                member_status = InMemoryMemberStatus(role_order=role_order)

        context = TeamContext(
            members=composed_members,
            config=config,
            supervisor=closed_supervisor,
            transport=transport,
            teammates=teammate_profiles,
            member_status=member_status,
            team_id=f"team-{process_val}",
            shared_memory=shared_store,
        )
        return TeamOrchestrator(context, resolved_strategy)
