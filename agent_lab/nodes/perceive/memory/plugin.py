"""perceive.memory — MemorySystem.perceive (Hub memory step)."""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="perceive.memory",
    layer=NodeLayer.PHASE,
    kind=NodeKind.TRANSFORMER,
    description="Call MemorySystem.perceive(state); emit memory ContextItems.",
    inputs=[
        PortInfo("memory_ref", kind=PortKind.FACT, required=False),
        PortInfo("state", kind=PortKind.FACT, required=False),
    ],
    outputs=[PortInfo("memory_items", kind=PortKind.FACT)],
    provides=["memory_items"],
    requires=["memory_system"],
    emits=["memory_items"],
    relates_to=["perceive.resolve", "perceive.trim"],
)
class PerceiveMemory(Node):
    name = "perceive.memory"

    def execute(self, node, inputs):
        from agent_lab.adapters.lca_perceive import fold_memory_items

        del node
        return fold_memory_items(
            memory_artifact=inputs.get("memory_ref"),
            state_artifact=inputs.get("state"),
        )
