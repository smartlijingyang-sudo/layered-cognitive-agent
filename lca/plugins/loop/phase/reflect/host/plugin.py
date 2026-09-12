"""phase.reflect host — subgraph entry node for the reflect phase.

Single-node subgraph host that runs the reflect phase logic. The
kernel enters ``bundles/reflect_subgraph.yaml`` here and dispatches
this NodeExecutor. The NodeExecutor adapts the typed port contract
to the standard phase executor's ``PhaseInput`` / ``PhaseResult``
shape; the kernel never sees that shape directly.

The standard plugin ``lca.plugins.loop.phase.reflect.standard.plugin``
owns the actual phase logic and is invoked via its ``create_executor``
factory.
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
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.loop.phase._shared.capabilities import StandardPhaseCapabilities
from lca.plugins.loop.phase._shared.reader import _MappingReader
from lca.plugins.loop.phase.reflect.standard.plugin import (
    StandardPhaseConfig,
    create_executor,
)


@dataclass(frozen=True, slots=True)
class ReflectHostExecutor:
    """Subgraph entry: pass through to the standard reflect phase executor.

    Reads the typed ``observation`` / ``decision`` ports and emits
    ``reflection`` so downstream ``remember.main`` can consume it.
    """

    semantic_name: str = "phase.reflect.host"
    region: str = "phase:reflect"
    declared_inputs: tuple[PortName, ...] = ("observation",)
    declared_outputs: tuple[PortName, ...] = ("reflection",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        from lca.contracts.protocols.declarative.declarative_2.declarative_phase_graph import (
            PhaseInput,
        )

        executor = create_executor()
        artifact = dict(input.port_values) or None
        phase_input = PhaseInput(artifact=artifact)
        capabilities = StandardPhaseCapabilities(_MappingReader(context.runtime))
        plan_ref = str(context.metadata.get("plan_ref", ""))
        node_id = str(context.metadata.get("node_id", "reflect.main"))
        from lca.contracts.models.core.state.state import AgentState, Budget
        from lca.harness.declarative.lifecycle.phase_context import (
            RestrictedPhaseContext,
        )

        state = AgentState(trace_id=plan_ref or "", task=node_id or "", budget=Budget())
        budget = state.budget
        phase_context = RestrictedPhaseContext(
            plan_ref=plan_ref,
            node_ref=node_id,
            state=state,
            journal=None,
            budget=budget,
            capabilities=_MappingReader(context.runtime),
            results_by_phase={},
        )
        result = await executor.execute(phase_context, phase_input)
        port_values: dict[PortName, object] = {}
        payload = getattr(result, "payload", None)
        if payload is not None:
            port_values["reflection"] = payload
        return NodeOutput(port_values=port_values, next_hint=None)


@plugin(
    id="phase.reflect.host",
    Config=StandardPhaseConfig,
    provides=("phase:reflect::phase.reflect.host",),
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
            descriptors=("phase_reflect_host.checked", "phase_reflect_host.served")
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: StandardPhaseConfig) -> None:
    ctx.provide("phase:reflect::phase.reflect.host", ReflectHostExecutor())


__all__ = ["ReflectHostExecutor", "setup"]
