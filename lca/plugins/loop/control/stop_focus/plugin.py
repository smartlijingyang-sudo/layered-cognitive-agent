"""control.stop.focus — NodeExecutor control node for the stop.focus slot.

Same stagnant-turn semantics as the previous standard executor, but
implemented as a NodeExecutor that emits a typed ``verdict`` port.
The new ``phase.stop.focus`` phase node owns the actual focus convergence
logic; this control node only emits the verdict that gates whether the
focus path may override the upstream stop decision.
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
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_1.ports import PortName
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.protocols.gate.control_verdict import ControlVerdict, ControlVerdictKind
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
class FocusStopExecutor:
    """Control node: emit ``verdict`` once consecutive stagnant turns reach limit."""

    semantic_name: str = "control.stop.focus"
    region: str = "phase:stop"
    declared_inputs: tuple[PortName, ...] = ()
    declared_outputs: tuple[PortName, ...] = ("verdict",)

    max_consecutive_stagnant_turns: int = 3

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        del input
        runtime = context.runtime or {}
        state = runtime.get("agent_state")
        history = getattr(state, "history", ()) or () if state is not None else ()
        count = _consecutive_stagnant_turns(history)
        if count >= self.max_consecutive_stagnant_turns:
            verdict = ControlVerdict(
                kind=ControlVerdictKind.STOP,
                detail=(
                    "cognitive focus policy stopped repeated unsuccessful intent "
                    f"after {count} consecutive stagnant turns "
                    f"(limit={self.max_consecutive_stagnant_turns})"
                ),
                plugin_id="control.stop.focus",
            )
            hint = "stop"
        else:
            verdict = ControlVerdict(
                kind=ControlVerdictKind.ALLOW,
                detail=(
                    "cognitive focus policy allows continuation "
                    f"(consecutive_stagnant_turns={count}, "
                    f"limit={self.max_consecutive_stagnant_turns})"
                ),
                plugin_id="control.stop.focus",
            )
            hint = None
        return NodeOutput(port_values={"verdict": verdict}, next_hint=hint)


@plugin(
    id="control.stop.focus",
    provides=("phase:stop::control.stop.focus",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    test_suite="tests/declarative/test_control_contributions.py",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G6_DECISION,
            control_slots=(ControlSlot.STOP_DECIDE,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.TURN,)),
        authority=AuthorityContract(grants=("turn.read",)),
        observability=EvidenceContract(
            descriptors=("control_stop_focus.checked", "control_stop_focus.served")
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
    """Mount the profile-configured, read-only focus governance executor."""
    # Keep config-driven ``max_consecutive_stagnant_turns`` parity with the
    # previous ``Config(max_consecutive_stagnant_turns=...)`` model: the
    # bundle YAML may set a custom limit; default 3 is the safe fallback.
    max_turns = 3
    if config is not None:
        max_attr = getattr(config, "max_consecutive_stagnant_turns", None)
        if isinstance(max_attr, int) and max_attr >= 1:
            max_turns = max_attr
    ctx.provide(
        "phase:stop::control.stop.focus",
        FocusStopExecutor(max_consecutive_stagnant_turns=max_turns),
    )


__all__ = ["FocusStopExecutor", "setup"]
