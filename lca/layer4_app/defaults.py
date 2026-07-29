"""Built-in default registrations for the LCA framework.

Idempotent — ``ensure_defaults()`` is safe to call multiple times; it only
registers on the first invocation.  This module also provides reusable
builder helpers (transport registry, team transport) that the composition
root (``assembly``) depends on.

Design invariant: this module NEVER imports from ``assembly.py``.
All brain/pipeline construction logic lives in ``brain_factory.py``.
"""

from __future__ import annotations

from lca.contracts.decision import Observation
from lca.contracts.enums import CompletionPolicyName, TeamProcess
from lca.contracts.lifecycle import TaskStatus
from lca.contracts.protocols import AgentTransport
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
from lca.layer4_app.brain_factory import DefaultBrainFactory


def build_default_transport_registry() -> TransportRegistry:
    """Build the default TransportRegistry with internal / a2a / mcp transports."""
    registry = TransportRegistry()
    registry.register(InternalTransport())
    registry.register(A2ATransport())
    registry.register(MCPTransport())
    return registry


def build_team_transport(
    members: list[BaseAgent],
) -> tuple[AgentTransport, str]:
    """Build an in-process transport and roster description for a team."""
    from lca.contracts.delegation_context import get_current_delegator

    transport = InternalTransport()
    for member in members:

        async def _handler(subtask: str, _m: BaseAgent = member) -> Observation:
            delegated_by = get_current_delegator()
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
    global_reg.register("delegation_ledger", "default", DelegationLedger)

    strategy_reg = get_global_strategy_registry()
    strategy_reg.register("default", DefaultBrainFactory())

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
    """Idempotent guard — registers defaults only on the first call.

    Invoked explicitly by ``Agent`` / ``MultiAgentTeam`` constructors.
    """
    if not defaults_registered():
        register_defaults()
