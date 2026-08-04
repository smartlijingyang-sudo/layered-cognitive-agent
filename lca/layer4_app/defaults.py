"""Built-in default registrations for the LCA framework.

register_defaults() registers factories on the given Registries.
Object-graph construction lives in composer.py (ADR-0030).

编排策略工厂统一签名为 ``(Coordination | None) -> TeamStrategy``：
参数化策略（Swarm / Debate / Graph）在 resolve 期从 Coordination 提取
构造参数，组合根因此不需要按策略键做 if/elif 特判（ADR-0033）。
"""

from __future__ import annotations

from lca.contracts.agent_spec import (
    BRAIN_CHOICE_DEFAULT,
    MEMORY_CHOICE_SIMPLE,
    OBSERVABILITY_CHOICE_CONSOLE,
    OBSERVABILITY_CHOICE_JSONL_FILE,
    STATE_STORE_CHOICE_MEMORY,
)
from lca.contracts.enums import ComponentKind, DecisionGateName
from lca.contracts.registries import Registries
from lca.contracts.team_coordination import (
    STRATEGY_KEY_DEBATE,
    STRATEGY_KEY_FAN_OUT,
    STRATEGY_KEY_GRAPH,
    STRATEGY_KEY_LEAD,
    STRATEGY_KEY_PEER_RELAY,
    STRATEGY_KEY_PEER_SWARM,
    STRATEGY_KEY_PIPELINE,
    Coordination,
    Graph,
    max_rounds_from_coordination,
)
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
from lca.layer3_agent.orchestration_registry import TeamStrategyRegistry
from lca.layer3_agent.orchestration_strategies import (
    DebateStrategy,
    GraphStrategy,
    HandoffStrategy,
    LeadStrategy,
    ParallelStrategy,
    SequentialStrategy,
    SwarmStrategy,
)
from lca.layer4_app.policies import LEAD_BUDGET_POLICY_KEY, LeadBudgetPolicy

EVENT_BUS_SIMPLE = "simple"
"""EventBus 内置注册名（组合根内部使用，非用户旋钮）。"""

MEMBER_STATUS_DEFAULT = "default"
"""MemberStatus 内置注册名（组合根内部使用，非用户旋钮）。"""


def _lead_strategy(_coordination: Coordination | None) -> LeadStrategy:
    return LeadStrategy()


def _pipeline_strategy(_coordination: Coordination | None) -> SequentialStrategy:
    return SequentialStrategy()


def _fan_out_strategy(_coordination: Coordination | None) -> ParallelStrategy:
    return ParallelStrategy(synthesizer=ConcatSynthesizer())


def _peer_relay_strategy(_coordination: Coordination | None) -> HandoffStrategy:
    return HandoffStrategy()


def _peer_swarm_strategy(coordination: Coordination | None) -> SwarmStrategy:
    rounds = max_rounds_from_coordination(coordination) if coordination is not None else None
    return SwarmStrategy(max_rounds=rounds)


def _debate_strategy(coordination: Coordination | None) -> DebateStrategy:
    rounds = max_rounds_from_coordination(coordination) if coordination is not None else None
    return DebateStrategy(max_rounds=rounds)


def _graph_strategy(coordination: Coordination | None) -> GraphStrategy:
    if not isinstance(coordination, Graph):
        raise TypeError(f"strategy {STRATEGY_KEY_GRAPH!r} requires Graph coordination")
    return GraphStrategy(execution_graph=coordination.execution_graph)


def register_defaults(registries: Registries) -> None:
    """Register built-in defaults into *registries* (idempotent overwrite)."""
    reg = registries.components
    reg.register(ComponentKind.OBSERVABILITY, OBSERVABILITY_CHOICE_CONSOLE, ConsoleObservability)
    reg.register(
        ComponentKind.OBSERVABILITY, OBSERVABILITY_CHOICE_JSONL_FILE, JSONLFileObservability
    )
    reg.register(ComponentKind.STATE_STORE, STATE_STORE_CHOICE_MEMORY, InMemoryStateStore)
    reg.register(ComponentKind.MEMORY, MEMORY_CHOICE_SIMPLE, SimpleMemorySystem)
    reg.register(ComponentKind.EVENT_BUS, EVENT_BUS_SIMPLE, SimpleEventBus)
    reg.register(ComponentKind.MEMBER_STATUS, MEMBER_STATUS_DEFAULT, InMemoryMemberStatus)

    registries.brain_factories.register(BRAIN_CHOICE_DEFAULT, SimpleBrainFactory())

    orch = registries.orchestration
    orch.register(STRATEGY_KEY_LEAD, _lead_strategy)
    orch.register(STRATEGY_KEY_PIPELINE, _pipeline_strategy)
    orch.register(STRATEGY_KEY_FAN_OUT, _fan_out_strategy)
    orch.register(STRATEGY_KEY_PEER_RELAY, _peer_relay_strategy)
    orch.register(STRATEGY_KEY_PEER_SWARM, _peer_swarm_strategy)
    orch.register(STRATEGY_KEY_DEBATE, _debate_strategy)
    orch.register(STRATEGY_KEY_GRAPH, _graph_strategy)

    reg.register(
        ComponentKind.DECISION_GATE, DecisionGateName.MUST_CONSULT_ALL, MustConsultAllMembers
    )
    reg.register(ComponentKind.BUDGET_POLICY, LEAD_BUDGET_POLICY_KEY, LeadBudgetPolicy)


def build_default_registries() -> Registries:
    """Fresh Registries with all built-in defaults registered."""
    registries = Registries(
        components=ComponentRegistry(),
        brain_factories=NamedRegistry(),
        orchestration=TeamStrategyRegistry(),
    )
    register_defaults(registries)
    return registries
