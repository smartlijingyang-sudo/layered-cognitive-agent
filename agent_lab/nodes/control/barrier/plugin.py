"""barrier node — single-slot pass-through; real BSP barrier lives in runtime scheduler."""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="barrier",
    layer=NodeLayer.CONTROL,
    kind=NodeKind.ROUTER,
    description="Single-slot pass-through. Real BSP barrier lives in runtime scheduler.",
    inputs=[PortInfo("from", kind=PortKind.ARTIFACT, required=False)],
    outputs=[PortInfo("to", kind=PortKind.ARTIFACT)],
    provides=["barrier_pass"],
    relates_to=["join"],
)
class Barrier(Node):
    """Single-slot pass-through. Real BSP barrier lives in runtime scheduler."""

    name = "barrier"

    def execute(self, node, inputs):
        src = node.config.get("from", node.ins[0])
        dst = node.config.get("to", node.outs[0])
        return {dst: inputs.get(src, Artifact(kind=ArtifactKind.TEXT, content=""))}
