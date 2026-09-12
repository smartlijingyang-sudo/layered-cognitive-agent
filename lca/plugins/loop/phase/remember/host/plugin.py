"""phase.remember host — subgraph entry node for the remember phase.

Single-node subgraph host that runs the remember phase logic. The
kernel enters ``bundles/remember_subgraph.yaml`` here and dispatches
this NodeExecutor. The NodeExecutor adapts the typed port contract
to the standard phase executor's ``PhaseInput`` / ``PhaseResult``
shape; the kernel never sees that shape directly.

The standard plugin ``lca.plugins.loop.phase.remember.standard.plugin``
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
from lca.plugins.loop.phase.remember.standard.plugin import (
    StandardPhaseConfig,
    create_executor,
)


@dataclass(frozen=True, slots=True)
class RememberHostExecutor:
    """Subgraph entry: pass through to the standard remember phase executor.

    Reads typed ports from upstream phases (decision, observation,
    reflection) and admits them to the memory layer. Emits no
    outgoing port — this is a terminal-of-typing node.
    """

    semantic_name: str = "phase.remember.host"
    region: str = "phase:remember"
    declared_inputs: tuple[PortName, ...] = ("decision", "observation", "reflection")
    declared_outputs: tuple[PortName, ...] = ()

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
        node_id = str(context.metadata.get("node_id", "remember.main"))
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
        await executor.execute(phase_context, phase_input)
        return NodeOutput(port_values={}, next_hint=None)


@plugin(
    id="phase.remember.host",
    Config=StandardPhaseConfig,
    provides=("phase:remember::phase.remember.host",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="memory",
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
            descriptors=("phase_remember_host.checked", "phase_remember_host.served")
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
    ctx.provide("phase:remember::phase.remember.host", RememberHostExecutor())


__all__ = ["RememberHostExecutor", "setup"]
