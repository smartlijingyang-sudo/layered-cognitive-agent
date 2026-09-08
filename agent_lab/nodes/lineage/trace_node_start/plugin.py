"""lineage__trace_node_start — 1 in 1 out passthrough + trace emit (stub)."""
from __future__ import annotations
from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="lineage__trace_node_start",
    layer=NodeLayer.LINEAGE,
    kind=NodeKind.PASSTHROUGH,
    description="Emit node_start trace; passthrough data (stub).",
    inputs=[PortInfo("in", kind=PortKind.ARTIFACT)],
    outputs=[PortInfo("out", kind=PortKind.ARTIFACT)],
)
class TraceNodeStart(Node):
    name = "lineage__trace_node_start"

    def execute(self, node, inputs):
        return {"out": inputs.get("in")}
