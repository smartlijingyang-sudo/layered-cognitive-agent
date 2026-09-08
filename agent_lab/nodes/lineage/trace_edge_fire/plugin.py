"""lineage__trace_edge_fire — 1 in 1 out passthrough + edge_fire trace (stub)."""
from __future__ import annotations
from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="lineage__trace_edge_fire",
    layer=NodeLayer.LINEAGE,
    kind=NodeKind.PASSTHROUGH,
    description="Emit edge_fire trace; passthrough data (stub).",
    inputs=[PortInfo("in", kind=PortKind.ARTIFACT)],
    outputs=[PortInfo("out", kind=PortKind.ARTIFACT)],
)
class TraceEdgeFire(Node):
    name = "lineage__trace_edge_fire"

    def execute(self, node, inputs):
        return {"out": inputs.get("in")}
