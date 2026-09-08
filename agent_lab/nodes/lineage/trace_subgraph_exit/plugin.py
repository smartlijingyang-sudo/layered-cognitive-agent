"""lineage__trace_subgraph_exit — 1 in 1 out passthrough + subgraph_exit trace (stub)."""
from __future__ import annotations
from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="lineage__trace_subgraph_exit",
    layer=NodeLayer.LINEAGE,
    kind=NodeKind.PASSTHROUGH,
    description="Emit subgraph_exit trace; passthrough data (stub).",
    inputs=[PortInfo("in", kind=PortKind.ARTIFACT)],
    outputs=[PortInfo("out", kind=PortKind.ARTIFACT)],
)
class TraceSubgraphExit(Node):
    name = "lineage__trace_subgraph_exit"

    def execute(self, node, inputs):
        return {"out": inputs.get("in")}
