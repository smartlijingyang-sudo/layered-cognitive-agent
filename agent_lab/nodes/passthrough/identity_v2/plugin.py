"""identity — 1 in 1 out passthrough. Returns the only input unchanged."""
from __future__ import annotations
from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="passthrough__identity",
    layer=NodeLayer.DIGEST,
    kind=NodeKind.PASSTHROUGH,
    description="Return the single input unchanged.",
    inputs=[PortInfo("in", kind=PortKind.ARTIFACT)],
    outputs=[PortInfo("out", kind=PortKind.ARTIFACT)],
)
class Identity(Node):
    name = "passthrough__identity"

    def execute(self, node, inputs):
        return {"out": inputs.get("in")}
