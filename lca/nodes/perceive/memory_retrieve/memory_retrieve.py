"""phase.perceive.memory_retrieve — declarative primitive: query and inject contextual memories.

ADR-0244: Retrieves semantic, episodic, and procedural memory context for the
current turn without hardcoded heuristics. Enriches the perceived manifest and
emits the typed ``memories`` port.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_1.ports import PortName
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.protocols.graph.routing import RoutingDecision
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


@dataclass(frozen=True, slots=True)
class PerceiveMemoryRetrieveExecutor:
    """Primitive: query memory provider / session store, emit memories and manifest."""

    semantic_name: str = "phase.perceive.memory_retrieve"
    region: str = "perceive"
    declared_inputs: tuple[PortName, ...] = ("manifest",)
    declared_outputs: tuple[PortName, ...] = ("manifest", "memories", "routing")

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        runtime = context.runtime or {}
        manifest = input.port_values.get("manifest")
        memory_provider = getattr(runtime, "memory_provider", None)
        if memory_provider is None and hasattr(runtime, "get"):
            memory_provider = runtime.get("memory_provider")

        memories: list[dict[str, Any]] = []
        if memory_provider is not None and hasattr(memory_provider, "retrieve"):
            try:
                retrieved = await memory_provider.retrieve(manifest=manifest)
                if isinstance(retrieved, (list, tuple)):
                    memories.extend(retrieved)
            except Exception as exc:
                _ = exc

        routing = RoutingDecision(action_type=ActionType.RESPOND)
        return NodeOutput(
            port_values={
                "manifest": manifest,
                "memories": tuple(memories),
                "routing": routing,
            }
        )


@plugin(
    id="phase.perceive.memory_retrieve",
    provides=("perceive::phase.perceive.memory_retrieve",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    test_suite="tests/integration/test_memory_and_procedural_distillation.py",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "phase_perceive_memory_retrieve.checked",
                "phase_perceive_memory_retrieve.served",
            )
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
    ctx.provide("perceive::phase.perceive.memory_retrieve", PerceiveMemoryRetrieveExecutor())


__all__ = ["PerceiveMemoryRetrieveExecutor", "setup"]
