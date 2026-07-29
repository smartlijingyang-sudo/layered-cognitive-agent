"""defaults.py —— 默认实现注册与可复用构建片段。

完整 Agent 对象图组装见 ``assembly.assemble_base_agent``（唯一共享管线入口）。
本模块负责：
1. ``ensure_defaults()`` 幂等注册发现型组件
2. Transport / Team 辅助构建
"""

from __future__ import annotations

from lca.contracts.action import ActionRegistryProtocol
from lca.contracts.decision import Observation
from lca.contracts.enums import CompletionPolicyName, TeamProcess
from lca.contracts.lifecycle import TaskStatus
from lca.contracts.protocols import AgentTransport, Body, Tool, TransportRegistryProtocol
from lca.contracts.role_team import ToolPermissionManifest
from lca.layer0_infra.component_registry import (
    defaults_registered,
    get_global_registry,
    mark_defaults_registered,
)
from lca.layer0_infra.observability.console_observability import ConsoleObservability
from lca.layer0_infra.observability.jsonl_file_observability import JSONLFileObservability
from lca.layer0_infra.state_store.in_memory_store import InMemoryStateStore
from lca.layer0_infra.transport.a2a_transport import A2ATransport
from lca.layer0_infra.transport.agent_transport import InternalTransport
from lca.layer0_infra.transport.mcp_transport import MCPTransport
from lca.layer0_infra.transport.transport_registry import TransportRegistry
from lca.layer1_cognitive.body.safe_executor import SimpleSafeExecutor
from lca.layer1_cognitive.body.tool_registry import SimpleToolRegistry
from lca.layer1_cognitive.brain.map_modules import (
    SimpleConflictMonitor,
    SimpleStateEvaluator,
    SimpleTaskCoordinator,
)
from lca.layer1_cognitive.brain.reasoner import build_team_roster
from lca.layer1_cognitive.brain.synthesizer import ConcatSynthesizer
from lca.layer1_cognitive.event_bus import SimpleEventBus
from lca.layer1_cognitive.memory.simple_memory import SimpleMemorySystem
from lca.layer1_cognitive.team_progress import DelegationLedger
from lca.layer2_runtime.strategy_registry import get_global_strategy_registry
from lca.layer3_agent.base_agent import BaseAgent
from lca.layer3_agent.orchestration_registry import get_global_orchestration_registry
from lca.layer3_agent.orchestration_strategies import (
    DebateStrategy,
    GraphStrategy,
    HandoffStrategy,
    HierarchicalStrategy,
    ParallelStrategy,
    SequentialStrategy,
)


def build_default_transport_registry() -> TransportRegistry:
    """构建默认 TransportRegistry：internal / a2a / mcp。"""
    registry = TransportRegistry()
    registry.register(InternalTransport())
    registry.register(A2ATransport())
    registry.register(MCPTransport())
    return registry


def build_body(
    tools: list[Tool],
    observability: object,
    transport_registry: TransportRegistryProtocol | None = None,
    action_registry: ActionRegistryProtocol | None = None,
    enable_fallback: bool = True,
) -> Body:
    """兼容构建器：创建**一份** ToolRegistry 并与 ActionRegistry 共享。

    新代码请优先用 ``assembly.build_body_from_shared`` / ``assemble_base_agent``。
    若传入 action_registry，则不再为其重建 UseTool 依赖——调用方须保证
    action_registry 已绑定同一 tool 管线；否则会用本函数新建的 registry 重建。
    """
    from lca.layer1_cognitive.body.action_catalog import build_default_action_registry
    from lca.layer4_app.assembly import build_body_from_shared, build_default_brain  # noqa: F401

    permission_manifest = ToolPermissionManifest(allowed_tools=[t.name for t in tools])
    tool_registry = SimpleToolRegistry()
    for t in tools:
        tool_registry.register(t)
    safe_executor = SimpleSafeExecutor(permission_manifest, observability)  # type: ignore[arg-type]
    registry = transport_registry or build_default_transport_registry()
    if action_registry is None:
        action_registry = build_default_action_registry(tool_registry, safe_executor, registry)
    return build_body_from_shared(
        tool_registry,
        safe_executor,
        registry,
        action_registry,
        enable_fallback=enable_fallback,
    )


def build_team_transport(
    members: list[BaseAgent],
) -> tuple[AgentTransport, str]:
    """为 hierarchical 团队构建进程内传输层和花名册。"""
    from lca.contracts.state import _current_delegator

    transport = InternalTransport()
    for member in members:

        async def _handler(subtask: str, _m: BaseAgent = member) -> Observation:
            delegated_by = _current_delegator.get()
            result = await _m.execute(subtask, delegated_by=delegated_by)
            return Observation(
                observation_id=f"obs_{result.trace_id}",
                success=result.status == TaskStatus.COMPLETED,
                payload=result.output,
                error=result.error,
            )

        transport.register_agent(member.role_profile.role, _handler)
    roster_desc = build_team_roster([m.role_profile for m in members])
    return transport, roster_desc


def register_defaults() -> None:
    """注册所有内置默认实现到全局注册表（可重复调用，幂等）。"""
    global_reg = get_global_registry()
    # 允许重复 register 覆盖同名实现
    global_reg.register("observability", "console", ConsoleObservability)
    global_reg.register("observability", "jsonl_file", JSONLFileObservability)
    global_reg.register("state_store", "memory", InMemoryStateStore)
    global_reg.register("memory", "simple", SimpleMemorySystem)
    global_reg.register("event_bus", "simple", SimpleEventBus)
    global_reg.register("delegation_ledger", "default", DelegationLedger)

    def _default_brain_factory(*args, **kwargs):  # type: ignore[no-untyped-def]
        from lca.layer4_app.assembly import build_default_brain

        return build_default_brain(*args, **kwargs)

    strategy_reg = get_global_strategy_registry()
    strategy_reg.register("default", _default_brain_factory)

    orch_reg = get_global_orchestration_registry()
    orch_reg.register(TeamProcess.HIERARCHICAL, HierarchicalStrategy)
    orch_reg.register(TeamProcess.SEQUENTIAL, SequentialStrategy)
    orch_reg.register(
        TeamProcess.PARALLEL, lambda: ParallelStrategy(synthesizer=ConcatSynthesizer())
    )
    orch_reg.register(TeamProcess.GRAPH, GraphStrategy)
    orch_reg.register(
        TeamProcess.DEBATE,
        lambda: DebateStrategy(
            conflict_monitor=SimpleConflictMonitor(),
            task_coordinator=SimpleTaskCoordinator(),
            state_evaluator=SimpleStateEvaluator(),
        ),
    )
    orch_reg.register(TeamProcess.HANDOFF, HandoffStrategy)

    from lca.layer1_cognitive.brain.completion_policies.roster_coverage import (
        RosterCoveragePolicy,
    )

    global_reg.register(
        "completion_policy", CompletionPolicyName.ROSTER_COVERAGE, RosterCoveragePolicy
    )
    mark_defaults_registered()


def ensure_defaults() -> None:
    """幂等：仅首次注册默认实现。由 Agent / MultiAgentTeam 构造时显式调用。"""
    if not defaults_registered():
        register_defaults()


def __getattr__(name: str) -> object:
    """兼容旧私有符号（_build_brain / _build_hooks / build_runtime）。"""
    if name == "_build_brain":
        from lca.layer4_app.assembly import build_default_brain

        return build_default_brain
    if name == "_build_hooks":
        from lca.layer4_app.assembly import build_hooks

        return build_hooks
    if name == "build_runtime":
        from lca.contracts.protocols import (
            BrainStrategy,
            HookRegistry,
            MemorySystem,
            StateStore,
            StepOutcomePolicy,
        )
        from lca.layer2_runtime.loop_judge import DefaultLoopJudge
        from lca.layer2_runtime.outcome_policies.default_outcome_policy import (
            DefaultStepOutcomePolicy,
        )
        from lca.layer2_runtime.runtime_loop import CognitiveRuntime

        def build_runtime(
            brain: BrainStrategy,
            body: Body,
            memory: MemorySystem,
            hooks: HookRegistry,
            state_store: StateStore,
            outcome_policy: StepOutcomePolicy | None = None,
        ) -> CognitiveRuntime:
            policy = outcome_policy or DefaultStepOutcomePolicy()
            return CognitiveRuntime(
                brain,
                body,
                memory,
                hooks,
                state_store,
                judge=DefaultLoopJudge(outcome_policy=policy),
            )

        return build_runtime
    raise AttributeError(name)
