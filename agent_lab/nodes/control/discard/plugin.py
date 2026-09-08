"""discard node — mark an artifact as discarded; pure no-op to audit sink."""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="discard",
    layer=NodeLayer.CONTROL,
    kind=NodeKind.PASSTHROUGH,
    description="Mark an artifact as discarded. Pure no-op pass-through to audit sink.",
    inputs=[PortInfo("from", kind=PortKind.ARTIFACT, required=False)],
    outputs=[PortInfo("to", kind=PortKind.FACT)],
    provides=["discard_marker"],
    relates_to=["integrate_observation"],
)
class Discard(Node):
    """Mark an artifact as discarded. Pure no-op pass-through to audit sink."""

    name = "discard"

    def execute(self, node, inputs):
        src = node.config.get("from", node.ins[0])
        out_port = node.config.get("to", node.outs[0])
        src_a = inputs.get(src)
        return {out_port: Artifact(
            kind=ArtifactKind.FACT,
            content={"discarded": True, "digest": src_a.short_id() if src_a else None},
            schema_ref="discard.v1",
        )}
