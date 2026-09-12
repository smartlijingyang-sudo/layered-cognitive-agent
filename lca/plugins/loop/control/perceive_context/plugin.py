"""control.perceive.context — NodeExecutor control node for the perceive slot.

ADR-0221: returns a typed ``verdict`` port. The subgraph topology wires
this node into the perceive flow (e.g. before ``perceive.fold``) and
routes the edge based on ``next_hint``.
"""

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
from lca.contracts.protocols.gate.control_verdict import ControlVerdict, ControlVerdictKind
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


@dataclass(frozen=True, slots=True)
class PerceiveContextExecutor:
    """Control node: allow / deny based on ``agent_state.status``."""

    semantic_name: str = "control.perceive.context"
    region: str = "phase:perceive"
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
        status = getattr(state, "status", TaskStatus.WORKING)
        if status != TaskStatus.WORKING:
            verdict = ControlVerdict(
                kind=ControlVerdictKind.STOP,
                detail="run state is not working",
                plugin_id="control.executor.perceive-context",
            )
        else:
            verdict = ControlVerdict(
                kind=ControlVerdictKind.ALLOW,
                detail="context assembly is permitted",
                plugin_id="control.executor.perceive-context",
            )
        return NodeOutput(
            port_values={"verdict": verdict},
            next_hint="stop" if verdict.kind == ControlVerdictKind.STOP else None,
        )


@plugin(
    id="control.perceive.context",
    provides=("phase:perceive::control.perceive.context",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    test_suite="tests/declarative/test_control_contributions.py",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G6_DECISION,
            control_slots=(ControlSlot.PERCEIVE_CONTEXT,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.TURN,)),
        authority=AuthorityContract(grants=("context.read",)),
        observability=EvidenceContract(
            descriptors=("control_perceive_context.checked", "control_perceive_context.served")
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
    ctx.provide("phase:perceive::control.perceive.context", PerceiveContextExecutor())


__all__ = ["PerceiveContextExecutor", "setup"]
