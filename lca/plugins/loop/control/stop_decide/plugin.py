"""control.stop.decide — NodeExecutor control node for the stop.decide slot."""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.enums.enums import ActionType
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
from lca.contracts.models.core.execution.decision import Decision
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


@dataclass(frozen=True, slots=True)
class StopDecideExecutor:
    """Control node: budget / decision action_type STOP; emit ``verdict``."""

    semantic_name: str = "control.stop.decide"
    region: str = "phase:stop"
    declared_inputs: tuple[PortName, ...] = ("decision",)
    declared_outputs: tuple[PortName, ...] = ("verdict",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        runtime = context.runtime or {}
        state = runtime.get("agent_state")
        budget = getattr(state, "budget", None) if state is not None else None
        decision = input.port_values.get("decision")
        if budget is not None and budget.exceeded():
            verdict = ControlVerdict(
                kind=ControlVerdictKind.STOP,
                detail="run budget is exhausted",
                plugin_id="control.executor.stop-decide",
            )
            hint = "stop"
        elif isinstance(decision, Decision) and decision.action_type == ActionType.STOP:
            verdict = ControlVerdict(
                kind=ControlVerdictKind.STOP,
                detail="decision requested terminal stop",
                plugin_id="control.executor.stop-decide",
            )
            hint = "stop"
        else:
            verdict = ControlVerdict(
                kind=ControlVerdictKind.ALLOW,
                detail="stop rule may continue",
                plugin_id="control.executor.stop-decide",
            )
            hint = None
        return NodeOutput(port_values={"verdict": verdict}, next_hint=hint)


@plugin(
    id="control.stop.decide",
    provides=("phase:stop::control.stop.decide",),
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
        authority=AuthorityContract(grants=("action.type.read",)),
        observability=EvidenceContract(
            descriptors=("control_stop_decide.checked", "control_stop_decide.served")
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
    ctx.provide("phase:stop::control.stop.decide", StopDecideExecutor())


__all__ = ["StopDecideExecutor", "setup"]
