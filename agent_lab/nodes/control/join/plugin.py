"""join node — wait for all required inputs, return one merged output."""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="join",
    layer=NodeLayer.CONTROL,
    kind=NodeKind.ROUTER,
    description="Wait for all required inputs, return one merged output.",
    inputs=[PortInfo("any_in", kind=PortKind.ARTIFACT, required=False)],
    outputs=[PortInfo("out", kind=PortKind.FACT)],
    provides=["joined_view"],
    relates_to=["barrier", "route_on"],
)
class Join(Node):
    """Wait for all required inputs, return one merged output."""

    name = "join"

    def execute(self, node, inputs):
        out_port = node.outs[0]
        merged: dict = {}
        for k, a in inputs.items():
            merged[k] = a.content
        return {out_port: Artifact(kind=ArtifactKind.FACT, content=merged, schema_ref="join.merged.v1")}
