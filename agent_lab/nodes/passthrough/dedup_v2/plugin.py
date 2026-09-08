"""dedup — 1 in 1 out: collapse duplicate lines from text content."""
from __future__ import annotations
from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="passthrough__dedup",
    layer=NodeLayer.DIGEST,
    kind=NodeKind.TRANSFORMER,
    description="Collapse duplicate lines (config.split_on) preserving order.",
    inputs=[PortInfo("text", kind=PortKind.TEXT)],
    outputs=[PortInfo("out", kind=PortKind.TEXT)],
)
class Dedup(Node):
    name = "passthrough__dedup"

    def execute(self, node, inputs):
        text_a = inputs.get("text")
        text = text_a.content if text_a else ""
        sep = node.config.get("split_on", "\n")
        lines = text.split(sep) if text else []
        seen: set = set()
        out: list = []
        for ln in lines:
            if ln not in seen:
                seen.add(ln)
                out.append(ln)
        joined = sep.join(out)
        return {"out": type(text_a)(kind=text_a.kind, content=joined, schema_ref=text_a.schema_ref) if text_a else None}
