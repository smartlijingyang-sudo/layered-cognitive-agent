"""Built-in default registrations for the LCA framework.

ADR-0024：不再有隐藏的模块级幂等标记。register_defaults() 对调用方传入的
Registries 实例做注册；对同一个 Registries 重复调用是安全的（覆盖写入相同的
工厂，无副作用），生命周期完全交给调用方（通常是 Assembly）决定。

本模块仍然只做发现型注册，不构造可运行对象图（见 assembly.py，ADR-0018）。
"""

from __future__ import annotations

from lca.contracts.enums import ComponentKind, DecisionGateName, TeamProcess
from lca.contracts.registries import Registries
from lca.layer0_infra.component_registry import ComponentRegistry, NamedRegistry
from lca.layer0_infra.observability.console_observability import ConsoleObservability
from lca.layer0_infra.observability.jsonl_file_observability import JSONLFileObservability
from lca.layer0_infra.state_store.in_memory_store import InMemoryStateStore
from lca.layer1_cognitive.brain.decision_gates import MustConsultAllMembers
from lca.layer1_cognitive.brain.default_factory import SimpleBrainFactory
from lca.layer1_cognitive.brain.synthesizer import ConcatSynthesizer
from lca.layer1_cognitive.event_bus import SimpleEventBus
from lca.layer1_cognitive.member_status import InMemoryMemberStatus
from lca.layer1_cognitive.memory.simple_memory import SimpleMemorySystem
from lca.layer3_agent.orchestration_registry import TeamProcessStrategyRegistry
from lca.layer3_agent.orchestration_strategies import (
    ChoreographyStrategy,
    GraphStrategy,
    HierarchicalStrategy,
)
from lca.layer4_app.policies import SupervisorBudgetPolicy


def register_defaults(registries: Registries) -> None:
    """把框架内置的默认实现注册进给定的 *registries*。

    幂等：对同一个 Registries 实例重复调用只是覆盖写入相同的工厂，无害。
    """
    reg = registries.components
    reg.register(ComponentKind.OBSERVABILITY, "console", ConsoleObservability)
    reg.register(ComponentKind.OBSERVABILITY, "jsonl_file", JSONLFileObservability)
    reg.register(ComponentKind.STATE_STORE, "memory", InMemoryStateStore)
    reg.register(ComponentKind.MEMORY, "simple", SimpleMemorySystem)
    reg.register(ComponentKind.EVENT_BUS, "simple", SimpleEventBus)
    reg.register(ComponentKind.MEMBER_STATUS, "default", InMemoryMemberStatus)

    registries.brain_factories.register("default", SimpleBrainFactory())

    orch = registries.orchestration
    orch.register(TeamProcess.HIERARCHICAL, HierarchicalStrategy)
    orch.register(TeamProcess.SEQUENTIAL, lambda: ChoreographyStrategy("sequential"))
    orch.register(
        TeamProcess.PARALLEL,
        lambda: ChoreographyStrategy("parallel", synthesizer=ConcatSynthesizer()),
    )
    orch.register(TeamProcess.GRAPH, GraphStrategy)
    orch.register(TeamProcess.DEBATE, lambda: ChoreographyStrategy("debate"))
    orch.register(TeamProcess.HANDOFF, lambda: ChoreographyStrategy("handoff"))

    reg.register(
        ComponentKind.DECISION_GATE, DecisionGateName.MUST_CONSULT_ALL, MustConsultAllMembers
    )
    reg.register(ComponentKind.BUDGET_POLICY, "supervisor", SupervisorBudgetPolicy())


def build_default_registries() -> Registries:
    """构造一份全新的、已注册全部内置默认实现的 Registries。

    这是"给我一份开箱即用的默认组合"的唯一入口 —— Assembly() 在未显式传入
    registries 时用它；测试或需要绕开 Assembly 直接构造 TeamOrchestrator
    的场景也可以直接调用它。
    """
    registries = Registries(
        components=ComponentRegistry(),
        brain_factories=NamedRegistry(),
        orchestration=TeamProcessStrategyRegistry(),
    )
    register_defaults(registries)
    return registries
