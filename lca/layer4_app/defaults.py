"""Built-in default registrations for the LCA framework.

Idempotent — ``ensure_defaults()`` is safe to call multiple times; it only
registers on the first invocation.  This module performs discovery-style
registration only — it does not construct runnable object graphs (see
``assembly.py``).
"""

from __future__ import annotations

from lca.contracts.enums import DecisionGateName, TeamProcess
from lca.layer0_infra.component_registry import (
    defaults_registered,
    get_global_registry,
    mark_defaults_registered,
)
from lca.layer0_infra.observability.console_observability import ConsoleObservability
from lca.layer0_infra.observability.jsonl_file_observability import JSONLFileObservability
from lca.layer0_infra.state_store.in_memory_store import InMemoryStateStore
from lca.layer1_cognitive.brain.decision_gates import MustConsultAllMembers
from lca.layer1_cognitive.brain.default_factory import SimpleBrainFactory
from lca.layer1_cognitive.brain.synthesizer import ConcatSynthesizer
from lca.layer1_cognitive.event_bus import SimpleEventBus
from lca.layer1_cognitive.member_status import InMemoryMemberStatus
from lca.layer1_cognitive.memory.simple_memory import SimpleMemorySystem
from lca.layer2_runtime.strategy_registry import get_global_brain_factory_registry
from lca.layer3_agent.orchestration_registry import get_global_orchestration_registry
from lca.layer3_agent.orchestration_strategies import (
    DebateStrategy,
    GraphStrategy,
    HandoffStrategy,
    HierarchicalStrategy,
    ParallelStrategy,
    SequentialStrategy,
)


def register_defaults() -> None:
    """Register all built-in default implementations into the global registry.

    Idempotent — calling multiple times simply overwrites with the same
    factories, which is harmless.
    """
    global_reg = get_global_registry()
    global_reg.register("observability", "console", ConsoleObservability)
    global_reg.register("observability", "jsonl_file", JSONLFileObservability)
    global_reg.register("state_store", "memory", InMemoryStateStore)
    global_reg.register("memory", "simple", SimpleMemorySystem)
    global_reg.register("event_bus", "simple", SimpleEventBus)
    global_reg.register("member_status", "default", InMemoryMemberStatus)
    # Transitional registry key — remove after one release cycle.
    global_reg.register("delegation_ledger", "default", InMemoryMemberStatus)

    strategy_reg = get_global_brain_factory_registry()
    strategy_reg.register("default", SimpleBrainFactory())

    orch_reg = get_global_orchestration_registry()
    orch_reg.register(TeamProcess.HIERARCHICAL, HierarchicalStrategy)
    orch_reg.register(TeamProcess.SEQUENTIAL, SequentialStrategy)
    orch_reg.register(
        TeamProcess.PARALLEL, lambda: ParallelStrategy(synthesizer=ConcatSynthesizer())
    )
    orch_reg.register(TeamProcess.GRAPH, GraphStrategy)
    orch_reg.register(TeamProcess.DEBATE, DebateStrategy)
    orch_reg.register(TeamProcess.HANDOFF, HandoffStrategy)

    global_reg.register("decision_gate", DecisionGateName.MUST_CONSULT_ALL, MustConsultAllMembers)
    # Transitional registry key
    global_reg.register(
        "completion_policy", DecisionGateName.MUST_CONSULT_ALL, MustConsultAllMembers
    )
    mark_defaults_registered()


def ensure_defaults() -> None:
    """Idempotent guard — registers defaults only on the first call.

    Invoked explicitly by ``Agent`` / ``MultiAgentTeam`` constructors.
    """
    if not defaults_registered():
        register_defaults()
