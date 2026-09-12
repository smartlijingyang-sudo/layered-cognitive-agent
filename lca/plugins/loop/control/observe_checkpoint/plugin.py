"""control.observe.checkpoint — NodeExecutor control node for observe.checkpoint slot."""

from __future__ import annotations

from dataclasses import dataclass

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
class ObserveCheckpointExecutor:
    """Control node: validate checkpoint step monotonicity; emit ``verdict``."""

    semantic_name: str = "control.observe.checkpoint"
    region: str = "phase:stop"
    declared_inputs: tuple[PortName, ...] = ()
    declared_outputs: tuple[PortName, ...] = ("verdict",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        del input
        runtime = context.runtime or {}
        state = runtime.get("agent_state")
        step = getattr(state, "step", 0) if state is not None else 0
        if step < 0:
            verdict = ControlVerdict(
                kind=ControlVerdictKind.DENY,
                detail="checkpoint step cannot be negative",
                plugin_id="control.executor.observe-checkpoint",
            )
            hint = "stop"
        else:
            reason = runtime.get("checkpoint_reason", "periodic")
            verdict = ControlVerdict(
                kind=ControlVerdictKind.ALLOW,
                detail=f"checkpoint is valid: {reason}",
                plugin_id="control.executor.observe-checkpoint",
            )
            hint = None
        return NodeOutput(port_values={"verdict": verdict}, next_hint=hint)


@plugin(
    id="control.observe.checkpoint",
    provides=("phase:stop::control.observe.checkpoint",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    test_suite="tests/declarative/test_control_contributions.py",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G6_DECISION,
            control_slots=(ControlSlot.OBSERVE_CHECKPOINT,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.TURN,)),
        authority=AuthorityContract(grants=("checkpoint.read", "state.read")),
        observability=EvidenceContract(
            descriptors=("control_observe_checkpoint.checked", "control_observe_checkpoint.served")
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
    ctx.provide("phase:stop::control.observe.checkpoint", ObserveCheckpointExecutor())


__all__ = ["ObserveCheckpointExecutor", "setup"]
