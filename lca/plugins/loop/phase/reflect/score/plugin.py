"""phase.reflect.score — primitive node: invoke brain / reflection pipeline.

ADR-0221: reads the typed ``observation`` port from upstream perceive and
emits a typed ``reflection`` payload. Prefers the
``cognitive_reflection_pipeline`` capability (LCA-default seam), falls back
to ``brain.reflect`` when no pipeline is wired.
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
from lca.contracts.protocols.think.cognition import Brain
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


@dataclass(frozen=True, slots=True)
class ReflectScoreExecutor:
    """Primitive: invoke the selected reflection seam, emit ``reflection``."""

    semantic_name: str = "phase.reflect.score"
    region: str = "phase:reflect"
    declared_inputs: tuple[PortName, ...] = ("observation",)
    declared_outputs: tuple[PortName, ...] = ("reflection",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        runtime = context.runtime or {}
        observation = input.port_values.get("observation")
        pipeline = runtime.get("cognitive_reflection_pipeline")
        brain = runtime.get("brain")
        payload: object | None = None
        if pipeline is not None and observation is not None:
            payload = await pipeline.reflect(
                state=runtime.get("agent_state"),
                observation=observation,
                critic=None,
            )
        elif isinstance(brain, Brain) and observation is not None:
            payload = await brain.reflect(runtime.get("agent_state"), observation)
        return NodeOutput(port_values={"reflection": payload}, next_hint=None)


@plugin(
    id="phase.reflect.score",
    provides=("phase:reflect::phase.reflect.score",),
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
            descriptors=("phase_reflect_score.checked", "phase_reflect_score.served")
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
    ctx.provide("phase:reflect::phase.reflect.score", ReflectScoreExecutor())


__all__ = ["ReflectScoreExecutor", "setup"]
