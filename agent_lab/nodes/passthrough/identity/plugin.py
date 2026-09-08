"""identity node — copy first input to first output (config may rename ports)."""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="identity",
    layer=NodeLayer.DIGEST,
    kind=NodeKind.PASSTHROUGH,
    description="Copy first input to first output (config may rename ports).",
    inputs=[PortInfo("from", kind=PortKind.ARTIFACT, required=False)],
    outputs=[PortInfo("to", kind=PortKind.ARTIFACT)],
    provides=["passthrough_copy"],
    relates_to=["assemble_messages", "merge_messages"],
)
class Identity(Node):
    """Copy first input to first output (config may rename ports)."""

    name = "identity"

    def execute(self, node, inputs):
        src = node.config.get("from", node.ins[0])
        dst = node.config.get("to", node.outs[0])
        if src not in inputs:
            return {dst: Artifact(kind=ArtifactKind.TEXT, content="")}
        return {dst: inputs[src]}
