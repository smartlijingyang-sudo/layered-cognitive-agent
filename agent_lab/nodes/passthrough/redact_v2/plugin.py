"""redact — 1 in 1 out: scrub known-sensitive patterns from text."""
from __future__ import annotations
from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="passthrough__redact",
    layer=NodeLayer.DIGEST,
    kind=NodeKind.TRANSFORMER,
    description="Replace known-sensitive patterns with [REDACTED] in text content.",
    inputs=[PortInfo("text", kind=PortKind.TEXT)],
    outputs=[PortInfo("out", kind=PortKind.TEXT)],
)
class Redact(Node):
    name = "passthrough__redact"

    def execute(self, node, inputs):
        text_a = inputs.get("text")
        text = text_a.content if text_a else ""
        for pat in node.config.get("patterns", []) or []:
            text = text.replace(pat, "[REDACTED]")
        return {"out": type(text_a)(kind=text_a.kind, content=text, schema_ref=text_a.schema_ref) if text_a else None}
