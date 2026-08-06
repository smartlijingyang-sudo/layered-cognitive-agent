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
    LeadMandate,
    PeerSwarm,
)
from lca.layer0_infra.component_registry import ComponentRegistry, NamedRegistry
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
    LeadStrategy,
    ParallelStrategy,
    RaceStrategy,
    SequentialStrategy,
    SwarmStrategy,
)
from lca.layer4_app.policies import LEAD_BUDGET_POLICY_KEY, LeadBudgetPolicy

EVENT_BUS_SIMPLE = "simple"
"""EventBus 内置注册名（组合根内部使用，非用户旋钮）。"""


_DUTY_MANDATES: frozenset[LeadMandate] = frozenset({LeadMandate.CONSULT, LeadMandate.BOARD})
"""携带咨询义务的授权（ADR-0035 / ADR-0036）：组合期决定 awareness 是否挂 ConsultDuty。"""


def _lead_strategy(assembly: TeamAssembly) -> LeadStrategy:
    governance = assembly.governance
    if not isinstance(governance, LeadSpec) or assembly.lead is None:
        raise TypeError(f"strategy {STRATEGY_KEY_LEAD!r} requires LeadSpec governance")
    members = assembly.stage.members
    roster = tuple(member.role_profile for member in members)
    role_order = tuple(member.role_profile.role for member in members)
    board = (
        InMemoryMemberStatus(role_order=role_order)
        if governance.mandate in _DUTY_MANDATES
        else None
    )
    return LeadStrategy(
        lead=assembly.lead,
        roster=roster,
        board=board,
        delegate_max_attempts=assembly.delegate_max_attempts,
    )


def _pipeline_strategy(assembly: TeamAssembly) -> SequentialStrategy:
    return SequentialStrategy(assembly.stage)


def _fan_out_strategy(assembly: TeamAssembly) -> ParallelStrategy:
    return ParallelStrategy(assembly.stage, synthesizer=ConcatSynthesizer())


def _peer_relay_strategy(assembly: TeamAssembly) -> RaceStrategy:
    return RaceStrategy(assembly.stage)


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
    """Register built-in defaults into *registries* (idempotent overwrite).

    可观测后端不在此注册：由 L0 ``observability.registry`` 统一管理
    （create_observability 唯一构造入口）。
    """
    reg = registries.components
    reg.register(ComponentKind.STATE_STORE, STATE_STORE_CHOICE_MEMORY, InMemoryStateStore)
    reg.register(ComponentKind.MEMORY, MEMORY_CHOICE_SIMPLE, SimpleMemorySystem)
    reg.register(ComponentKind.EVENT_BUS, EVENT_BUS_SIMPLE, SimpleEventBus)

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
