"""prefix — 1 in 1 out: prepend a string to text content."""
from __future__ import annotations
from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="passthrough__prefix",
    layer=NodeLayer.DIGEST,
    kind=NodeKind.TRANSFORMER,
    description="Prepend config.text to the input text content.",
    inputs=[PortInfo("text", kind=PortKind.TEXT)],
    outputs=[PortInfo("out", kind=PortKind.TEXT)],
)
class Prefix(Node):
    name = "passthrough__prefix"

    def execute(self, node, inputs):
        text_a = inputs.get("text")
        text = text_a.content if text_a else ""
        prefixed = (node.config.get("text", "") or "") + (text or "")
        return {"out": type(text_a)(kind=text_a.kind, content=prefixed, schema_ref=text_a.schema_ref) if text_a else None}
