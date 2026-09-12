"""phase.stop.fail — primitive: decode PhaseExecutionFailure → typed StopDecision.

ADR-0221: optional entry node for the stop subgraph when the
PhaseExecutionPolicy runner emits a typed ``PhaseExecutionFailure`` as
an upstream artifact. Decodes it into a typed ``StopDecision(STOP,
ERROR, RunDiagnostic)`` — same wire shape as the previous
``phase_failure_stop_result``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from lca.contracts.atoms.control.slot import ControlSlot
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


def _failure_to_stop_decision(artifact: object) -> StopDecision:
    """Decode a carried ``PhaseExecutionFailure`` into a typed StopDecision."""
    attempts = tuple(getattr(artifact, "attempts", ()) or ())
    error_kind = getattr(artifact, "error_kind", "internal") or "internal"
    node_id = str(getattr(artifact, "node_id", "") or "")
    last_message = ""
    for attempt in reversed(attempts):
        msg = getattr(attempt, "error_message", "") or ""
        if msg:
            last_message = msg
            break
    categories = ",".join(
        f"{getattr(a, 'attempt', '?')}:{getattr(a, 'category', '?')}:{getattr(a, 'error_type', '?')}"
        for a in attempts
    )
    summary = (
        f"node={node_id} error_kind={error_kind} "
        f"attempts={len(attempts)}[{categories}]"
        + (f" | {last_message}" if last_message else "")
    )
    from lca.runtime.support.diagnostic import RunDiagnostic

    diagnostic = RunDiagnostic(
        run_id="",
        trace_id="",
        phase="stop",
        node_id=node_id,
        error_type=getattr(attempts[-1], "error_type", "UnknownError") if attempts else "UnknownError",
        message=summary,
        stack=(),
        causation=(),
        attempts=tuple(
            type("AttemptSummary", (), {
                "attempt": getattr(a, "attempt", 0),
                "category": getattr(a, "category", "permanent"),
                "error_type": getattr(a, "error_type", "UnknownError"),
                "message": getattr(a, "error_message", None) or None,
            })()
            for a in attempts
        ),
        suggested_action=None,
        extra=(("error_kind", error_kind),),
    )
    return StopDecision(
        should_stop=True,
        reason=StopReason.ERROR,
        status=TaskStatus.FAILED,
        failure=diagnostic,
    )


@dataclass(frozen=True, slots=True)
class StopFailExecutor:
    """Primitive: typed PhaseExecutionFailure → typed StopDecision."""

    semantic_name: str = "phase.stop.fail"
    region: str = "phase:stop"
    declared_inputs: tuple[PortName, ...] = ("artifact",)
    declared_outputs: tuple[PortName, ...] = ("stop_decision",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        del context
        artifact = input.port_values.get("artifact")
        if artifact is None:
            return NodeOutput(port_values={"stop_decision": None}, next_hint=None)
        if not (isinstance(artifact, Mapping) or hasattr(artifact, "attempts")):
            return NodeOutput(port_values={"stop_decision": None}, next_hint=None)
        return NodeOutput(
            port_values={"stop_decision": _failure_to_stop_decision(artifact)},
            next_hint=None,
        )


@plugin(
    id="phase.stop.fail",
    provides=("phase:stop::phase.stop.fail",),
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
            descriptors=("phase_stop_fail.checked", "phase_stop_fail.served")
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
    ctx.provide("phase:stop::phase.stop.fail", StopFailExecutor())


__all__ = ["StopFailExecutor", "setup", "_failure_to_stop_decision"]
