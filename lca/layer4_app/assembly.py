"""AgentAssembly —— L4 唯一对象图工厂。

保证 ToolRegistry / SafeExecutor / ActionRegistry / TransportRegistry
在 Brain（DecisionParser）与 Body（UseToolOperation）之间共享同一实例。
"""

from __future__ import annotations

from typing import cast

from lca.contracts.action import ActionRegistryProtocol
from lca.contracts.protocols import (
    Body,
    BrainStrategy,
    EventBus,
    LLMAdapter,
    MemorySystem,
    Observability,
    StateStore,
    TeamEntrypoint,
    Tool,
    TransportRegistryProtocol,
)
from lca.contracts.role_team import RoleProfile, ToolPermissionManifest
from lca.layer0_infra.component_registry import ComponentRegistry, get_global_registry
from lca.layer1_cognitive.body.action_catalog import (
    build_default_action_registry,
    format_allowed_actions_desc,
)
from lca.layer1_cognitive.body.fallback_decorated_body import FallbackDecoratedBody
from lca.layer1_cognitive.body.safe_executor import SimpleSafeExecutor
from lca.layer1_cognitive.body.simple_body import SimpleBody
from lca.layer1_cognitive.body.tool_registry import SimpleToolRegistry
from lca.layer1_cognitive.brain.candidate_evaluation_pipeline import (
    SimpleCandidateEvaluationPipeline,
)
from lca.layer1_cognitive.brain.critic import SimpleCritic
from lca.layer1_cognitive.brain.decision_parser import SimpleDecisionParser
from lca.layer1_cognitive.brain.modular_brain import ModularBrain
from lca.layer1_cognitive.brain.prompts import load_builtin_prompt
from lca.layer1_cognitive.brain.reasoner import SimpleReasoner
from lca.layer1_cognitive.hook_registry import SimpleHookRegistry, default_logging_hook
from lca.layer1_cognitive.prompt_manager import SimplePromptManager
from lca.layer2_runtime.fallback_handler import FallbackActionPolicy
from lca.layer2_runtime.hooks import HOOK_NAMES, make_event_emitting_hook
from lca.layer2_runtime.outcome_policies.default_outcome_policy import DefaultStepOutcomePolicy
from lca.layer2_runtime.runtime_loop import CognitiveRuntime
from lca.layer2_runtime.strategy_registry import get_global_strategy_registry
from lca.layer3_agent.base_agent import BaseAgent


def _resolve_component(reg: ComponentRegistry, category: str, value: str | object) -> object:
    if isinstance(value, str):
        return reg.require(category, value)()
    return value


def build_default_brain(
    llm: LLMAdapter,
    role_profile: RoleProfile,
    tools_desc: str,
    team_roster: str | None = None,
    action_registry: ActionRegistryProtocol | None = None,
) -> ModularBrain:
    """默认 Brain 工厂：ModularBrain + MAP 五模块。"""
    prompt_manager = SimplePromptManager()
    prompt_manager.register_template("react_prompt", load_builtin_prompt("react_prompt"))
    prompt_manager.register_template(
        "hierarchical_prompt", load_builtin_prompt("hierarchical_prompt")
    )

    allowed_actions_desc = ""
    if action_registry is not None:
        allowed_actions_desc = format_allowed_actions_desc(action_registry.allowed_action_types())

    reasoner = SimpleReasoner(
        llm,
        prompt_manager,
        role_profile,
        tools_desc,
        team_roster=team_roster,
        allowed_actions_desc=allowed_actions_desc,
    )
    return ModularBrain(
        reasoner=reasoner,
        decision_parser=SimpleDecisionParser(action_registry=action_registry),
        critic=SimpleCritic(),
        evaluation_pipeline=SimpleCandidateEvaluationPipeline(),
    )


def build_body_from_shared(
    tool_registry: SimpleToolRegistry,
    safe_executor: SimpleSafeExecutor,
    transport_registry: object,
    action_registry: ActionRegistryProtocol,
    *,
    enable_fallback: bool = True,
) -> Body:
    """用**已共享**的依赖构建 Body，禁止内部再 new ToolRegistry。"""
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
    max_steps: int = 10,
    max_wall_clock_seconds: int | None = 300,
    memory: str | MemorySystem = "simple",
    observability: str | Observability = "console",
    state_store: str | StateStore = "memory",
    brain_strategy: str | BrainStrategy = "default",
) -> BaseAgent:
    """组装完整 BaseAgent；所有执行管线共享同一套 registry。"""
    from lca.layer4_app.defaults import build_default_transport_registry, ensure_defaults

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

    # ── 单一共享管线 ──────────────────────────────────────────────
    tool_registry = SimpleToolRegistry()
    for t in tools:
        tool_registry.register(t)
    safe_executor = SimpleSafeExecutor(permission_manifest, obs)
    transport_registry = build_default_transport_registry()
    action_registry = build_default_action_registry(
        tool_registry, safe_executor, transport_registry
    )

    # Brain
    brain: BrainStrategy
    if isinstance(brain_strategy, str):
        strategy_reg = get_global_strategy_registry()
        if brain_strategy not in strategy_reg:
            raise ValueError(
                f"Unknown brain_strategy: {brain_strategy!r}. Available: {strategy_reg.list()}"
            )
        tools_desc = ", ".join(t.name for t in tools) or "(无可用工具)"
        # 默认工厂仍走 build_default_brain，确保 action_registry 共享
        factory = strategy_reg.resolve(brain_strategy)
        if brain_strategy == "default":
            brain = build_default_brain(
                llm, role_profile, tools_desc, action_registry=action_registry
            )
        else:
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
        outcome_policy=DefaultStepOutcomePolicy(),
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
    process: object | None = None,
    supervisor: BaseAgent | None = None,
    max_rounds: int | None = None,
    shared_memory_layers: list[str] | None = None,
    graph_definition_ref: str | None = None,
    strategy: object | None = None,
) -> TeamEntrypoint:
    """组装团队对象图。"""
    from lca.contracts.enums import TeamProcess
    from lca.contracts.role_team import TeamConfig
    from lca.layer3_agent.supervisor import Supervisor as SupervisorImpl
    from lca.layer3_agent.team_orchestrator import TeamOrchestrator
    from lca.layer4_app.defaults import build_team_transport, ensure_defaults

    ensure_defaults()
    process_val = process if process is not None else TeamProcess.HIERARCHICAL
    config = TeamConfig(
        process=process_val,  # type: ignore[arg-type]
        max_rounds=max_rounds,
        shared_memory_layers=list(shared_memory_layers or []),
        graph_definition_ref=graph_definition_ref,
    )
    base_supervisor: SupervisorImpl | None = None
    if supervisor is not None:
        if isinstance(supervisor, SupervisorImpl):
            base_supervisor = supervisor
        else:
            base_supervisor = SupervisorImpl(
                supervisor.runtime,
                supervisor.role_profile,
                max_steps=max(getattr(supervisor, "max_steps", 10), 20),
                max_wall_clock_seconds=300,
            )
    transport, roster_desc = build_team_transport(members)
    return TeamOrchestrator(
        members,
        config,
        base_supervisor,
        transport=transport,
        roster_desc=roster_desc,
        strategy=strategy,  # type: ignore[arg-type]
    )
