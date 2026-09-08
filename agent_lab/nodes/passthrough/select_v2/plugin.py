"""select — 1 in 1 out: pick one field from a dict-content artifact."""
from __future__ import annotations
from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="passthrough__select",
    layer=NodeLayer.DIGEST,
    kind=NodeKind.PASSTHROUGH,
    description="Pick one field from the input artifact's content dict.",
    inputs=[PortInfo("in", kind=PortKind.ARTIFACT)],
    outputs=[PortInfo("out", kind=PortKind.ARTIFACT)],
)
class Select(Node):
    name = "passthrough__select"

    def execute(self, node, inputs):
        in_a = inputs.get("in")
        field = node.config.get("field", "")
        content = in_a.content if in_a else {}
        if isinstance(content, dict):
            return {"out": content.get(field)}
        return {"out": None}
