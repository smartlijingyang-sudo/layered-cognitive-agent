"""phase.perceive.observe — primitive node: invoke PerceiveHub, emit raw manifest.

ADR-0221: this is the lowest-level node in the perceive subgraph. It
calls the profile-selected ``perceive_hub`` capability and emits a
typed ``manifest`` port. The next node (``phase.perceive.fold``)
collapses the manifest into the closed ``observation`` shape.
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
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_1.ports import PortName
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.protocols.think.cognition import PerceiveHub
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


@dataclass(frozen=True, slots=True)
class PerceiveObserveExecutor:
    """Primitive: invoke the PerceiveHub capability; emit raw ``manifest``."""

    semantic_name: str = "phase.perceive.observe"
    region: str = "phase:perceive"
    declared_inputs: tuple[PortName, ...] = ()
    declared_outputs: tuple[PortName, ...] = ("manifest",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        del input
        runtime = context.runtime or {}
        hub = runtime.get("perceive_hub")
        if not isinstance(hub, PerceiveHub):
            return NodeOutput(port_values={"manifest": None}, next_hint=None)
        agent_state = runtime.get("agent_state")
        manifest = await hub.perceive(agent_state)  # type: ignore[arg-type]
        return NodeOutput(port_values={"manifest": manifest}, next_hint=None)


@plugin(
    id="phase.perceive.observe",
    provides=("phase:perceive::phase.perceive.observe",),
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
            descriptors=("phase_perceive_observe.checked", "phase_perceive_observe.served")
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
    ctx.provide("phase:perceive::phase.perceive.observe", PerceiveObserveExecutor())


__all__ = ["PerceiveObserveExecutor", "setup"]
