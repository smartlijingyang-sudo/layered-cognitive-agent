"""redact node — remove or mask lines that match a set of patterns."""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="redact",
    layer=NodeLayer.MODEL_VISIBLE,
    kind=NodeKind.TRANSFORMER,
    description="Remove or mask lines that match any of config.patterns.",
    inputs=[PortInfo("from", kind=PortKind.ARTIFACT, required=False)],
    outputs=[PortInfo("to", kind=PortKind.TEXT)],
    provides=["redacted_text"],
    relates_to=["trust_classify", "dedup", "rank"],
)
class Redact(Node):
    """Remove or mask lines that match any of config.patterns."""

    name = "redact"

    def execute(self, node, inputs):
        src = node.config.get("from", node.ins[0])
        dst = node.config.get("to", node.outs[0])
        patterns = list(node.config.get("patterns", []) or [])
        src_a = inputs.get(src)
        if src_a is None:
            return {dst: Artifact(kind=ArtifactKind.TEXT, content="")}
        text = str(src_a.content)
        for pat in patterns:
            text = text.replace(pat, "[REDACTED]")
        return {dst: Artifact(kind=ArtifactKind.TEXT, content=text, schema_ref="redacted.v1")}
