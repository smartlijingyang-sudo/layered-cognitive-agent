"""rank — 1 in 1 out: keep top-K lines from text content."""
from __future__ import annotations
from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="passthrough__rank",
    layer=NodeLayer.DIGEST,
    kind=NodeKind.TRANSFORMER,
    description="Keep top-K lines (config.keep); drop the rest.",
    inputs=[PortInfo("text", kind=PortKind.TEXT)],
    outputs=[PortInfo("out", kind=PortKind.TEXT)],
)
class Rank(Node):
    name = "passthrough__rank"

    def execute(self, node, inputs):
        text_a = inputs.get("text")
        text = text_a.content if text_a else ""
        sep = node.config.get("split_on", "\n")
        keep = int(node.config.get("keep", 50))
        lines = text.split(sep) if text else []
        joined = sep.join(lines[:keep])
        return {"out": type(text_a)(kind=text_a.kind, content=joined, schema_ref=text_a.schema_ref) if text_a else None}
