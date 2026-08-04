"""Built-in default registrations for the LCA framework.

register_defaults() registers factories on the given Registries.
Object-graph construction lives in composer.py (ADR-0030).

编排策略工厂统一签名为 ``(TeamAssembly) -> TeamStrategy``（ADR-0034）：
工厂在 resolve 期从组合期闭合的装配视图中取所需（stage / lead /
governance 参数），把所有治理方式——含 lead——闭合为封闭策略。
组合根因此既不需要按策略键做 if/elif 特判，也不编排 lead 专属布线。
"""

from __future__ import annotations

from lca.contracts.agent_spec import (
    BRAIN_CHOICE_DEFAULT,
    MEMORY_CHOICE_SIMPLE,
    OBSERVABILITY_CHOICE_CONSOLE,
    OBSERVABILITY_CHOICE_JSONL_FILE,
    STATE_STORE_CHOICE_MEMORY,
    LeadSpec,
)
from lca.contracts.enums import ComponentKind, DecisionGateName
from lca.contracts.protocols import TeamAssembly
from lca.contracts.registries import Registries
from lca.contracts.team_coordination import (
    STRATEGY_KEY_DEBATE,
    STRATEGY_KEY_FAN_OUT,
    STRATEGY_KEY_GRAPH,
    STRATEGY_KEY_LEAD,
    STRATEGY_KEY_PEER_RELAY,
    STRATEGY_KEY_PEER_SWARM,
    STRATEGY_KEY_PIPELINE,
    Debate,
    Graph,
    PeerSwarm,
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


def _lead_strategy(assembly: TeamAssembly) -> LeadStrategy:
    governance = assembly.governance
    if not isinstance(governance, LeadSpec) or assembly.lead is None:
        raise TypeError(f"strategy {STRATEGY_KEY_LEAD!r} requires LeadSpec governance")
    members = assembly.stage.members
    roster = tuple(member.role_profile for member in members)
    role_order = tuple(member.role_profile.role for member in members)
    return LeadStrategy(
        lead=assembly.lead,
        mandate=governance.mandate,
        roster=roster,
        board=InMemoryMemberStatus(role_order=role_order),
        delegate_max_attempts=assembly.delegate_max_attempts,
    )


def _pipeline_strategy(assembly: TeamAssembly) -> SequentialStrategy:
    return SequentialStrategy(assembly.stage)


def _fan_out_strategy(assembly: TeamAssembly) -> ParallelStrategy:
    return ParallelStrategy(assembly.stage, synthesizer=ConcatSynthesizer())


def _peer_relay_strategy(assembly: TeamAssembly) -> HandoffStrategy:
    return HandoffStrategy(assembly.stage)


def _peer_swarm_strategy(assembly: TeamAssembly) -> SwarmStrategy:
    governance = assembly.governance
    if not isinstance(governance, PeerSwarm):
        raise TypeError(f"strategy {STRATEGY_KEY_PEER_SWARM!r} requires PeerSwarm governance")
    return SwarmStrategy(assembly.stage, max_rounds=governance.max_rounds)


def _debate_strategy(assembly: TeamAssembly) -> DebateStrategy:
    governance = assembly.governance
    if not isinstance(governance, Debate):
        raise TypeError(f"strategy {STRATEGY_KEY_DEBATE!r} requires Debate governance")
    return DebateStrategy(assembly.stage, max_rounds=governance.max_rounds)


def _graph_strategy(assembly: TeamAssembly) -> GraphStrategy:
    governance = assembly.governance
    if not isinstance(governance, Graph):
        raise TypeError(f"strategy {STRATEGY_KEY_GRAPH!r} requires Graph governance")
    return GraphStrategy(assembly.stage, execution_graph=governance.execution_graph)


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
