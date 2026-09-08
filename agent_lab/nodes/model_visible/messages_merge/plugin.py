"""model_visible__messages_merge — 2 in 1 out: merge two message-list streams."""
from __future__ import annotations
from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="model_visible__messages_merge",
    layer=NodeLayer.MODEL_VISIBLE,
    kind=NodeKind.ASSEMBLER,
    description="Merge two message-list artifacts into one list (preserves role).",
    inputs=[
        PortInfo("messages_a", kind=PortKind.MESSAGE, required=False),
        PortInfo("messages_b", kind=PortKind.MESSAGE, required=False),
    ],
    outputs=[PortInfo("messages", kind=PortKind.MESSAGE)],
)
class MessagesMerge(Node):
    name = "model_visible__messages_merge"

    def execute(self, node, inputs):
        a = inputs.get("messages_a")
        b = inputs.get("messages_b")
        merged = []
        for src in (a, b):
            if src and isinstance(src.content, list):
                merged.extend(m for m in src.content if isinstance(m, dict))
        return {"messages": a.__class__(kind=a.kind, content=merged, schema_ref=a.schema_ref) if a else (b or None)}
