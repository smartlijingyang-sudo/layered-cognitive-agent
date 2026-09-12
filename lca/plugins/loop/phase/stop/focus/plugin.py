"""phase.stop.focus — primitive: consecutive-stagnant-turn convergence.

ADR-0221: reads ``stop_decision`` (from upstream ``stop.should_check``)
plus the agent's recent ``Turn`` history (read from ``agent_state`` via
runtime) and emits a typed ``stop_payload`` port. Convergence rule
matches the previous ``FocusStopExecutor``: a turn is stagnant when its
observation is unsuccessful and its reflection reports
``NEEDS_CORRECTION`` / ``BLOCKED``; only a *consecutive run* of
unchanged-intent stagnant turns triggers a ``STOP`` rewrite.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.enums.enums import ReflectionVerdict
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.core.execution.decision import Decision, Turn
from lca.contracts.models.core.policy.stop import StopDecision, StopReason
from lca.contracts.models.core.state.lifecycle import TaskStatus
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_1.ports import PortName
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


def _is_stagnant(turn: Turn) -> bool:
    reflection = turn.reflection
    return (
        not turn.observation.success
        and reflection is not None
        and reflection.verdict in {ReflectionVerdict.NEEDS_CORRECTION, ReflectionVerdict.BLOCKED}
    )


def _intent_signature(decision: Decision) -> tuple[object, ...]:
    action_type = str(decision.action_type)
    tool_names = tuple(call.tool_name for call in decision.tool_calls)
    delegation_targets = tuple(
        (delegation.target_role, delegation.target_agent_id) for delegation in decision.delegations
    )
    response = decision.response_text.strip() if decision.response_text else ""
    return action_type, tool_names, delegation_targets, response


def _consecutive_stagnant_turns(history: Iterable[object]) -> int:
    expected_intent: tuple[object, ...] | None = None
    count = 0
    for item in reversed(tuple(history)):
        if not isinstance(item, Turn) or not _is_stagnant(item):
            break
        intent = _intent_signature(item.decision)
        if expected_intent is None:
            expected_intent = intent
        elif intent != expected_intent:
            break
        count += 1
    return count


@dataclass(frozen=True, slots=True)
class StopFocusExecutor:
    """Primitive: stagnant-turn convergence; emit typed ``stop_payload``."""

    semantic_name: str = "phase.stop.focus"
    region: str = "phase:stop"
    declared_inputs: tuple[PortName, ...] = ("stop_decision", "memory_receipt")
    declared_outputs: tuple[PortName, ...] = ("stop_payload",)

    max_consecutive_stagnant_turns: int = 3

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        runtime = context.runtime or {}
        state = runtime.get("agent_state")
        upstream_stop = input.port_values.get("stop_decision")
        if not isinstance(upstream_stop, StopDecision):
            return NodeOutput(port_values={"stop_payload": upstream_stop}, next_hint=None)
        history = getattr(state, "history", ()) or ()
        stagnant = _consecutive_stagnant_turns(history)
        if stagnant < self.max_consecutive_stagnant_turns:
            return NodeOutput(port_values={"stop_payload": upstream_stop}, next_hint=None)
        # Override the upstream stop with a focus-driven STOP.
        focused = StopDecision(
            should_stop=True,
            reason=StopReason.ERROR,
            status=TaskStatus.FAILED,
            failure=None,
        )
        return NodeOutput(port_values={"stop_payload": focused}, next_hint=None)


@plugin(
    id="phase.stop.focus",
    provides=("phase:stop::phase.stop.focus",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    test_suite="tests/declarative/test_phase_subgraph_parity.py",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("phase_stop_focus.checked", "phase_stop_focus.served")
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: object) -> None:
    del config
    ctx.provide("phase:stop::phase.stop.focus", StopFocusExecutor())


__all__ = ["StopFocusExecutor", "setup"]
