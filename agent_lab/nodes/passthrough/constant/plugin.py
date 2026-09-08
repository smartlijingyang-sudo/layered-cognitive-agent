"""constant node — emit a constant Artifact on the first output."""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import make_text


@node(
    id="constant",
    layer=NodeLayer.DIGEST,
    kind=NodeKind.PRODUCER,
    description="Emit a constant Artifact on the first output.",
    inputs=[],
    outputs=[PortInfo("out", kind=PortKind.TEXT)],
    provides=["constant_artifact"],
)
class Constant(Node):
    """Emit a constant Artifact on the first output."""

    name = "constant"

    def execute(self, node, inputs):
        dst = node.outs[0]
        return {dst: make_text(str(node.config.get("value", "")), schema_ref=node.config.get("schema_ref", "raw"))}
