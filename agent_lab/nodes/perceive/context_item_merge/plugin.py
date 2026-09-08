"""perceive__context_item_merge — 2 in 1 out: union multiple ContextItem feeds.

Real implementation concatenates input ContextItem lists into one.
"""
from __future__ import annotations
from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="perceive__context_item_merge",
    layer=NodeLayer.MODEL_VISIBLE,
    kind=NodeKind.ASSEMBLER,
    description="Merge multiple ContextItem feeds into one list.",
    inputs=[
        PortInfo("items_a", kind=PortKind.FACT, required=False),
        PortInfo("items_b", kind=PortKind.FACT, required=False),
    ],
    outputs=[PortInfo("items", kind=PortKind.FACT)],
)
class ContextItemMerge(Node):
    name = "perceive__context_item_merge"

    def execute(self, node, inputs):
        a = inputs.get("items_a")
        b = inputs.get("items_b")
        merged = []
        if a and isinstance(a.content, list):
            merged.extend(a.content)
        if b and isinstance(b.content, list):
            merged.extend(b.content)
        return {"items": a.__class__(kind=a.kind, content=merged, schema_ref=a.schema_ref) if a else (b or None)}
