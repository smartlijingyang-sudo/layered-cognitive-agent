"""Composition root — wires all layers into a working object graph.

Sole module that assembles the full Agent / Team object graphs via the
``Assembly`` class. Entry points: ``Assembly.assemble_agent`` (single agent),
``Assembly.assemble_team`` (team).

Team transport channel builders live in ``team_wiring`` and are re-exported
here for a stable composition-root import path.
"""

from __future__ import annotations

from typing import TypeVar

from lca.contracts.action import ActionRegistryProtocol
from lca.contracts.budget import (
    DEFAULT_MAX_STEPS,
    DEFAULT_MAX_WALL_CLOCK_SECONDS,
)
from lca.contracts.enums import (
    ComponentKind,
    DecisionGateName,
    HookEvent,
    MemoryLayer,
    TeamProcess,
)
from lca.contracts.graph import ExecutionGraph
from lca.contracts.mechanisms import ComponentRegistryProtocol
from lca.contracts.orchestration_taxonomy import (
    SupervisorPlane,
    assert_supervisor_plane_gate_compatible,
)
from lca.contracts.protocols import (
    Body,
    Brain,
    BrainFactory,
    BudgetPolicy,
    EventBus,
    LLMAdapter,
    MemorySystem,
    Observability,
    StateStore,
    TeamProcessStrategy,
    TeamUnit,
    Tool,
    TransportRegistryProtocol,
)
from lca.contracts.registries import Registries
from lca.contracts.role_team import RoleProfile, TeamConfig, ToolPermissionManifest
from lca.layer1_cognitive.body.action_catalog import build_default_action_registry
from lca.layer1_cognitive.body.fallback_decorated_body import FallbackDecoratedBody
from lca.layer1_cognitive.body.fallback_policy import FallbackActionPolicy
from lca.layer1_cognitive.body.safe_executor import SimpleSafeExecutor
from lca.layer1_cognitive.body.simple_body import SimpleBody
from lca.layer1_cognitive.body.tool_registry import SimpleToolRegistry
from lca.layer1_cognitive.hook_registry import SimpleHookRegistry, default_logging_hook
from lca.layer2_runtime.default_stop_rule import DefaultStopRule
from lca.layer2_runtime.event_emission import make_event_emitting_hook
from lca.layer2_runtime.outcome_policies.default_outcome_policy import DefaultStopOutcomePolicy
from lca.layer2_runtime.runtime_loop import CognitiveRuntime
from lca.layer3_agent.cognitive_agent import CognitiveAgent
from lca.layer3_agent.orchestration_registry import OrchestrationFactory
from lca.layer3_agent.orchestration_strategies.graph import GraphStrategy
from lca.layer4_app.defaults import build_default_registries
from lca.layer4_app.team_wiring import (
    build_default_transport_registry,
    build_team_transport,
)

# Stable re-exports for tests and progressive-disclosure imports.
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
    """Resolve a component from registry or use as-is, with runtime type check."""
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
    """Build Body from *already-shared* pipeline components.

    The caller must pass the **same** ToolRegistry / SafeExecutor /
    TransportRegistry / ActionRegistry instances that are shared with the
    Brain — never let Body create its own copies.
    """
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
    """Build the default HookRegistry with logging + event-emitting hooks."""
    hooks = SimpleHookRegistry(observability)
    event_hook = make_event_emitting_hook(event_bus)
    for event_name in HookEvent:
        hooks.register(event_name, default_logging_hook)
        hooks.register(event_name, event_hook)
    return hooks


def _promote_supervisor(supervisor: CognitiveAgent, policy: BudgetPolicy) -> CognitiveAgent:
    """Apply supervisor budget floors via the registered BudgetPolicy."""
    limits = policy.resolve(supervisor)
    return CognitiveAgent(
        supervisor.runtime,
        supervisor.role_profile,
        max_steps=limits.max_steps,
        max_wall_clock_seconds=limits.max_wall_clock_seconds,
    )


class Assembly:
    """组合根的显式对象化版本（ADR-0024）。

    持有一份私有的 Registries，不读写任何进程级全局状态。未显式传入
    registries 时，构造一份包含全部内置默认实现的新 Registries
    （见 defaults.build_default_registries）——传入自定义 registries 时，
    按传入的原样使用，不会偷偷叠加内置默认值。
    """

    def __init__(self, registries: Registries | None = None) -> None:
        self._registries = registries if registries is not None else build_default_registries()

    @property
    def registries(self) -> Registries:
        return self._registries

    def register_component(self, category: str, name: str, impl: object) -> None:
        """向本 Assembly 的组件注册表注册自定义实现。

        替代过去"直接改全局 ComponentRegistry"的用法（见 pluggability_demo）。
        """
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
    ) -> CognitiveAgent:
        """Assemble a complete CognitiveAgent with a single shared pipeline.

        Creates one set of ToolRegistry / SafeExecutor / TransportRegistry /
        ActionRegistry and injects them into both Brain and Body, guaranteeing
        they operate on the same instances. All string-keyed components
        (*memory*, *observability*, *state_store*) are resolved via this
        Assembly's ComponentRegistry.
        """
        reg = self._registries.components

        permission_manifest = ToolPermissionManifest(allowed_tools=[t.name for t in tools])
        role_profile = RoleProfile(
            role=role,
            goal=goal,
            backstory=backstory,
            tool_permission_manifest=permission_manifest,
        )

        # runtime_checkable Protocols support isinstance at runtime; mypy limitation #9208
        obs = _resolve_component(reg, ComponentKind.OBSERVABILITY, observability, Observability)  # type: ignore[type-abstract]
        mem = _resolve_component(reg, ComponentKind.MEMORY, memory, MemorySystem)  # type: ignore[type-abstract]
        ss = _resolve_component(reg, ComponentKind.STATE_STORE, state_store, StateStore)  # type: ignore[type-abstract]

        tool_registry = SimpleToolRegistry()
        for t in tools:
            tool_registry.register(t)
        safe_executor = SimpleSafeExecutor(permission_manifest, obs)
        transport_registry = build_default_transport_registry()
        action_registry = build_default_action_registry(
            tool_registry, safe_executor, transport_registry
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
        decision_gate: DecisionGateName | None = None,
        supervisor_plane: SupervisorPlane | None = None,
        delegate_max_attempts: int | None = None,
    ) -> TeamUnit:
        """Assemble a team object graph from *members* with the given *process*.

        Settlement / plane knobs (ADR-0027) are orthogonal to *process*:
        free supervisor = default gate none; consultation compliance =
        ``decision_gate=must_consult_all``.

        ``process=GRAPH`` requires ``execution_graph`` (or an explicit *strategy*).
        """
        from lca.layer3_agent.team_orchestrator import TeamOrchestrator

        process_val = process if process is not None else TeamProcess.HIERARCHICAL
        gate = decision_gate if decision_gate is not None else DecisionGateName.NONE
        plane = supervisor_plane if supervisor_plane is not None else SupervisorPlane.CONSULTATION
        assert_supervisor_plane_gate_compatible(plane, gate)

        config = TeamConfig(
            process=process_val,
            max_rounds=max_rounds,
            shared_memory_layers=list(shared_memory_layers or []),
            decision_gate=gate,
            supervisor_plane=plane,
        )
        if delegate_max_attempts is not None:
            config.delegate_max_attempts = delegate_max_attempts

        resolved_strategy = strategy
        if resolved_strategy is None and process_val is TeamProcess.GRAPH:
            if execution_graph is None:
                raise ValueError(
                    "process=GRAPH requires execution_graph= (or pass strategy=GraphStrategy(...))"
                )
            resolved_strategy = GraphStrategy(execution_graph=execution_graph)

        base_supervisor: CognitiveAgent | None = None
        if supervisor is not None:
            policy = _resolve_component(
                self._registries.components,
                ComponentKind.BUDGET_POLICY,
                "supervisor",
                BudgetPolicy,  # type: ignore[type-abstract]
            )
            base_supervisor = _promote_supervisor(supervisor, policy)
        transport = build_team_transport(members)
        teammate_profiles = [m.role_profile for m in members]

        return TeamOrchestrator(
            members,
            config,
            registries=self._registries,
            supervisor=base_supervisor,
            transport=transport,
            teammates=teammate_profiles,
            strategy=resolved_strategy,
        )
