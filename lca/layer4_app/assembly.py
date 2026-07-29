"""Composition root — wires all layers into a working object graph.

This is the **only** module that assembles the full Agent / Team object
graphs.  It guarantees that the shared pipeline components (ToolRegistry,
SafeExecutor, ActionRegistry, TransportRegistry) are created once and
injected into both Brain and Body, so they always operate on the same
instances.

High-level entry points:

* ``assemble_base_agent`` — builds a single ``BaseAgent``.
* ``assemble_team`` — builds a ``TeamEntrypoint`` from a list of members.

Lower-level builders (``build_body_from_shared``, ``build_hooks``) are
exposed for advanced / test scenarios.
"""

from __future__ import annotations

from typing import cast

from lca.contracts.action import ActionRegistryProtocol
from lca.contracts.budget import DEFAULT_MAX_STEPS
from lca.contracts.enums import TeamProcess
from lca.contracts.protocols import (
    Body,
    BrainStrategy,
    EventBus,
    LLMAdapter,
    MemorySystem,
    Observability,
    OrchestrationStrategy,
    StateStore,
    TeamEntrypoint,
    Tool,
    TransportRegistryProtocol,
)
from lca.contracts.role_team import RoleProfile, TeamConfig, ToolPermissionManifest
from lca.layer0_infra.component_registry import ComponentRegistry, get_global_registry
from lca.layer1_cognitive.body.action_catalog import build_default_action_registry
from lca.layer1_cognitive.body.fallback_decorated_body import FallbackDecoratedBody
from lca.layer1_cognitive.body.safe_executor import SimpleSafeExecutor
from lca.layer1_cognitive.body.simple_body import SimpleBody
from lca.layer1_cognitive.body.tool_registry import SimpleToolRegistry
from lca.layer1_cognitive.hook_registry import SimpleHookRegistry, default_logging_hook
from lca.layer2_runtime.default_loop_judge import DefaultLoopJudge
from lca.layer2_runtime.event_emission import HOOK_NAMES, make_event_emitting_hook
from lca.layer2_runtime.fallback_handler import FallbackActionPolicy
from lca.layer2_runtime.outcome_policies.default_outcome_policy import DefaultStepOutcomePolicy
from lca.layer2_runtime.runtime_loop import CognitiveRuntime
from lca.layer2_runtime.strategy_registry import get_global_strategy_registry
from lca.layer3_agent.base_agent import BaseAgent
from lca.layer4_app.defaults import (
    build_default_transport_registry,
    build_team_transport,
    ensure_defaults,
)

# Default wall-clock timeout for agent assembly (seconds).
_ASSEMBLY_MAX_WALL_CLOCK_SECONDS: int = 300
# Minimum step budget when an agent is promoted to team supervisor.
_SUPERVISOR_MIN_MAX_STEPS: int = 20


def _resolve_component(reg: ComponentRegistry, category: str, value: str | object) -> object:
    """Resolve *value* from *reg* if it is a string key, otherwise return as-is."""
    if isinstance(value, str):
        return reg.require(category, value)()
    return value


def build_body_from_shared(
    tool_registry: SimpleToolRegistry,
    safe_executor: SimpleSafeExecutor,
    transport_registry: object,
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
        transport_registry=cast("TransportRegistryProtocol", transport_registry),
        action_registry=action_registry,
    )
    if enable_fallback:
        return FallbackDecoratedBody(inner=simple_body, fallback_handler=FallbackActionPolicy())
    return simple_body


def build_hooks(observability: Observability, event_bus: EventBus) -> SimpleHookRegistry:
    """Build the default HookRegistry with logging + event-emitting hooks."""
    hooks = SimpleHookRegistry(observability)
    event_hook = make_event_emitting_hook(event_bus)
    for event_name in HOOK_NAMES:
        hooks.register(event_name, default_logging_hook)
        hooks.register(event_name, event_hook)
    return hooks


def assemble_base_agent(
    *,
    role: str,
    goal: str,
    backstory: str,
    tools: list[Tool],
    llm: LLMAdapter,
    max_steps: int = DEFAULT_MAX_STEPS,
    max_wall_clock_seconds: int | None = _ASSEMBLY_MAX_WALL_CLOCK_SECONDS,
    memory: str | MemorySystem = "simple",
    observability: str | Observability = "console",
    state_store: str | StateStore = "memory",
    brain_strategy: str | BrainStrategy = "default",
) -> BaseAgent:
    """Assemble a complete BaseAgent with a single shared pipeline.

    Creates one set of ToolRegistry / SafeExecutor / TransportRegistry /
    ActionRegistry and injects them into both Brain and Body, guaranteeing
    they operate on the same instances.  All string-keyed components
    (*memory*, *observability*, *state_store*) are resolved via the global
    ComponentRegistry.
    """
    ensure_defaults()
    reg = get_global_registry()

    permission_manifest = ToolPermissionManifest(allowed_tools=[t.name for t in tools])
    role_profile = RoleProfile(
        role=role,
        goal=goal,
        backstory=backstory,
        tool_permission_manifest=permission_manifest,
    )

    obs = cast("Observability", _resolve_component(reg, "observability", observability))
    mem = cast("MemorySystem", _resolve_component(reg, "memory", memory))
    ss = cast("StateStore", _resolve_component(reg, "state_store", state_store))

    # ── Single shared pipeline ────────────────────────────────────────────
    tool_registry = SimpleToolRegistry()
    for t in tools:
        tool_registry.register(t)
    safe_executor = SimpleSafeExecutor(permission_manifest, obs)
    transport_registry = build_default_transport_registry()
    action_registry = build_default_action_registry(
        tool_registry, safe_executor, transport_registry
    )

    # Brain — resolve via strategy registry (unified path for all strategies)
    brain: BrainStrategy
    if isinstance(brain_strategy, str):
        strategy_reg = get_global_strategy_registry()
        if brain_strategy not in strategy_reg:
            raise ValueError(
                f"Unknown brain_strategy: {brain_strategy!r}. Available: {strategy_reg.list()}"
            )
        tools_desc = ", ".join(t.name for t in tools) or "(no tools available)"
        factory = strategy_reg.resolve(brain_strategy)
        brain = factory(llm, role_profile, tools_desc, action_registry=action_registry)
    else:
        brain = brain_strategy

    body = build_body_from_shared(
        tool_registry,
        safe_executor,
        transport_registry,
        action_registry,
    )
    event_bus = cast("EventBus", _resolve_component(reg, "event_bus", "simple"))
    hooks = build_hooks(obs, event_bus)
    runtime = CognitiveRuntime(
        brain,
        body,
        mem,
        hooks,
        ss,
        judge=DefaultLoopJudge(outcome_policy=DefaultStepOutcomePolicy()),
    )
    return BaseAgent(
        runtime,
        role_profile,
        max_steps=max_steps,
        max_wall_clock_seconds=max_wall_clock_seconds,
    )


def assemble_team(
    *,
    members: list[BaseAgent],
    process: TeamProcess | None = None,
    supervisor: BaseAgent | None = None,
    max_rounds: int | None = None,
    shared_memory_layers: list[str] | None = None,
    graph_definition_ref: str | None = None,
    strategy: OrchestrationStrategy | None = None,
) -> TeamEntrypoint:
    """Assemble a team object graph from *members* with the given *process*."""
    from lca.layer3_agent.team_orchestrator import TeamOrchestrator

    ensure_defaults()
    process_val = process if process is not None else TeamProcess.HIERARCHICAL
    config = TeamConfig(
        process=process_val,
        max_rounds=max_rounds,
        shared_memory_layers=list(shared_memory_layers or []),
        graph_definition_ref=graph_definition_ref,
    )
    base_supervisor: BaseAgent | None = None
    if supervisor is not None:
        base_supervisor = BaseAgent(
            supervisor.runtime,
            supervisor.role_profile,
            max_steps=max(
                getattr(supervisor, "max_steps", DEFAULT_MAX_STEPS),
                _SUPERVISOR_MIN_MAX_STEPS,
            ),
            max_wall_clock_seconds=_ASSEMBLY_MAX_WALL_CLOCK_SECONDS,
        )
    transport, roster_desc = build_team_transport(members)
    return TeamOrchestrator(
        members,
        config,
        base_supervisor,
        transport=transport,
        roster_desc=roster_desc,
        strategy=strategy,
    )
