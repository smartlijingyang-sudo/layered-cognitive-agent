"""select node — pick one input port by config.key, copy its content into one output."""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="select",
    layer=NodeLayer.DIGEST,
    kind=NodeKind.PASSTHROUGH,
    description="Pick one input port by config.key, copy its content into one output.",
    inputs=[PortInfo("from", kind=PortKind.ARTIFACT, required=False)],
    outputs=[PortInfo("to", kind=PortKind.ARTIFACT)],
    provides=["port_select"],
    relates_to=["identity"],
)
class Select(Node):
    """Pick one input port by config.key, copy its content into one output."""

    name = "select"

    def execute(self, node, inputs):
        src = node.config.get("key", node.ins[0])
        dst = node.config.get("to", node.outs[0])
        if src not in inputs:
            return {dst: Artifact(kind=ArtifactKind.TEXT, content="")}
        return {dst: inputs[src]}
