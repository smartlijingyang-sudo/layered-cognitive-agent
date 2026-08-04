"""Built-in default registrations for the LCA framework.

register_defaults() registers factories on the given Registries.
Object-graph construction lives in composer.py (ADR-0030).
"""

from __future__ import annotations

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
from lca.layer4_app.policies import LeadBudgetPolicy


def register_defaults(registries: Registries) -> None:
    """Register built-in defaults into *registries* (idempotent overwrite)."""
    reg = registries.components
    reg.register(ComponentKind.OBSERVABILITY, "console", ConsoleObservability)
    reg.register(ComponentKind.OBSERVABILITY, "jsonl_file", JSONLFileObservability)
    reg.register(ComponentKind.STATE_STORE, "memory", InMemoryStateStore)
    reg.register(ComponentKind.MEMORY, "simple", SimpleMemorySystem)
    reg.register(ComponentKind.EVENT_BUS, "simple", SimpleEventBus)
    reg.register(ComponentKind.MEMBER_STATUS, "default", InMemoryMemberStatus)

    registries.brain_factories.register("default", SimpleBrainFactory())

    orch = registries.orchestration
    orch.register(STRATEGY_KEY_LEAD, LeadStrategy)
    orch.register(STRATEGY_KEY_PIPELINE, SequentialStrategy)
    orch.register(STRATEGY_KEY_FAN_OUT, lambda: ParallelStrategy(synthesizer=ConcatSynthesizer()))
    orch.register(STRATEGY_KEY_DEBATE, DebateStrategy)
    orch.register(STRATEGY_KEY_PEER_RELAY, HandoffStrategy)
    orch.register(STRATEGY_KEY_PEER_SWARM, SwarmStrategy)
    orch.register(STRATEGY_KEY_GRAPH, GraphStrategy)

    reg.register(
        ComponentKind.DECISION_GATE, DecisionGateName.MUST_CONSULT_ALL, MustConsultAllMembers
    )
    reg.register(ComponentKind.BUDGET_POLICY, "lead", LeadBudgetPolicy)


def build_default_registries() -> Registries:
    """Fresh Registries with all built-in defaults registered."""
    registries = Registries(
        components=ComponentRegistry(),
        brain_factories=NamedRegistry(),
        orchestration=TeamStrategyRegistry(),
    )
    register_defaults(registries)
    return registries
