"""defaults.py —— 唯一允许 import 所有具体类的组装根。

把框架内置的默认实现注册进全局 ComponentRegistry / StrategyRegistry，
使得 Agent(...) 可以通过名字字符串选择实现，
也允许用户在调用 Agent 之前注册自己的实现。
"""

from __future__ import annotations

from lca.contracts.decision import Observation
from lca.contracts.protocols import (
    AgentTransport,
    Body,
    BrainStrategy,
    EventBus,
    HookRegistryP,
    LLMAdapter,
    MemorySystem,
    Observability,
    StateStore,
    ToolProtocol,
)
from lca.contracts.role_team import RoleProfile, ToolPermissionManifest
from lca.layer0_infra.observability.console_observability import ConsoleObservability
from lca.layer0_infra.registry import get_global_registry
from lca.layer0_infra.state_mgmt.in_memory_store import InMemoryStateStore
from lca.layer0_infra.transport.agent_transport import InternalTransport
from lca.layer1_cognitive.body.safe_executor import SimpleSafeExecutor
from lca.layer1_cognitive.body.simple_body import SimpleBody
from lca.layer1_cognitive.body.tool_registry import SimpleToolRegistry
from lca.layer1_cognitive.brain.critic import SimpleCritic
from lca.layer1_cognitive.brain.decision_parser import SimpleDecisionParser
from lca.layer1_cognitive.brain.map_modules import (
    SimpleConflictMonitor,
    SimpleStateEvaluator,
    SimpleStatePredictor,
    SimpleTaskCoordinator,
    SimpleTaskDecomposer,
)
from lca.layer1_cognitive.brain.modular_brain import ModularBrain
from lca.layer1_cognitive.brain.reasoner import (
    DEFAULT_REACT_TEMPLATE,
    HIERARCHICAL_DELEGATE_TEMPLATE,
    SimpleReasoner,
    build_team_roster,
)
from lca.layer1_cognitive.event_bus import SimpleEventBus
from lca.layer1_cognitive.hook_registry import SimpleHookRegistry, default_logging_hook
from lca.layer1_cognitive.memory.simple_memory import SimpleMemorySystem
from lca.layer1_cognitive.prompt_manager import SimplePromptManager
from lca.layer2_runtime.hooks import HOOK_NAMES
from lca.layer2_runtime.runtime_loop import CognitiveRuntime
from lca.layer2_runtime.strategy_registry import get_global_strategy_registry
from lca.layer3_agent.base_agent import BaseAgent


def _build_brain(
    llm: LLMAdapter,
    role_profile: RoleProfile,
    tools_desc: str,
    team_roster: str | None = None,
) -> ModularBrain:
    """默认 Brain 工厂：ModularBrain + MAP 五模块。"""
    prompt_manager = SimplePromptManager()
    prompt_manager.register_template("react_prompt", DEFAULT_REACT_TEMPLATE)
    prompt_manager.register_template("hierarchical_prompt", HIERARCHICAL_DELEGATE_TEMPLATE)
    reasoner = SimpleReasoner(
        llm, prompt_manager, role_profile, tools_desc, team_roster=team_roster
    )
    return ModularBrain(
        reasoner=reasoner,
        decision_parser=SimpleDecisionParser(),
        critic=SimpleCritic(),
        task_decomposer=SimpleTaskDecomposer(),
        state_predictor=SimpleStatePredictor(),
        state_evaluator=SimpleStateEvaluator(),
        conflict_monitor=SimpleConflictMonitor(),
        task_coordinator=SimpleTaskCoordinator(),
    )


def build_body(tools: list[ToolProtocol], observability: Observability) -> SimpleBody:
    """默认 Body 构建器。"""
    permission_manifest = ToolPermissionManifest(allowed_tools=[t.name for t in tools])
    tool_registry = SimpleToolRegistry()
    for t in tools:
        tool_registry.register(t)
    safe_executor = SimpleSafeExecutor(permission_manifest, observability)
    return SimpleBody(tool_registry, safe_executor)


def _build_hooks(observability: Observability) -> SimpleHookRegistry:
    hooks = SimpleHookRegistry(observability)
    for event_name in HOOK_NAMES:
        hooks.register(event_name, default_logging_hook)
    return hooks


def build_runtime(
    brain: BrainStrategy,
    body: Body,
    memory: MemorySystem,
    hooks: HookRegistryP,
    event_bus: EventBus,
    state_store: StateStore,
) -> CognitiveRuntime:
    """默认 Runtime 构建器。"""
    return CognitiveRuntime(brain, body, memory, hooks, event_bus, state_store)


def build_team_transport(
    members: list[BaseAgent],
) -> tuple[AgentTransport, str]:
    """为 hierarchical 团队构建进程内传输层和花名册。

    把每个 member 的 execute 包装为 async handler（key = role），
    Result → Observation 的适配在此完成；
    同时拼接 roster_desc 供 Supervisor 的 Reasoner 感知队友。
    """
    transport = InternalTransport()
    for member in members:

        async def _handler(subtask: str, _m: BaseAgent = member) -> Observation:
            result = await _m.execute(subtask)
            return Observation(
                observation_id=f"obs_{result.trace_id}",
                success=result.status == "completed",
                payload=result.output,
                error=result.error,
            )

        transport.register_agent(member.role_profile.role, _handler)
    roster_desc = build_team_roster([m.role_profile for m in members])
    return transport, roster_desc


def register_defaults() -> None:
    """注册所有内置默认实现到全局注册表。"""
    reg = get_global_registry()
    reg.register("observability", "console", ConsoleObservability)
    reg.register("state_store", "memory", InMemoryStateStore)
    reg.register("memory", "simple", SimpleMemorySystem)
    reg.register("event_bus", "simple", SimpleEventBus)

    strategy_reg = get_global_strategy_registry()
    strategy_reg.register("default", _build_brain)


register_defaults()
