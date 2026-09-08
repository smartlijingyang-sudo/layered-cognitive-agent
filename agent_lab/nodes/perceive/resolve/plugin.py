"""perceive.resolve — resolve Sensor list + MemorySystem for the Hub fold."""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="perceive.resolve",
    layer=NodeLayer.PHASE,
    kind=NodeKind.ASSEMBLER,
    description=(
        "Resolve Sensor list + MemorySystem (PerceiveService.assemble seam). "
        "No sensor read, no memory query."
    ),
    inputs=[PortInfo("state", kind=PortKind.FACT, required=False)],
    outputs=[
        PortInfo("sensors", kind=PortKind.FACT),
        PortInfo("memory_ref", kind=PortKind.FACT),
    ],
    provides=["perceive_sensors", "memory_system"],
    requires=["perceive_service"],
    emits=["sensors", "memory_ref"],
    relates_to=["perceive.sense", "perceive.memory"],
)
class PerceiveResolve(Node):
    name = "perceive.resolve"

    def execute(self, node, inputs):
        from agent_lab.adapters.lca_perceive import LcaPerceiveResolveProvider

        del inputs  # resolve is config-driven; state is for lineage only
        provider = LcaPerceiveResolveProvider.from_node_config(
            getattr(node, "config", None) or {}
        )
        return provider.resolve()
