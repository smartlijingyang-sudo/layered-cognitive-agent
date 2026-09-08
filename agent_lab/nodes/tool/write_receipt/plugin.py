"""write_receipt node — pass-through the receipt; hook point for journaling later."""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="write_receipt",
    layer=NodeLayer.EFFECT,
    kind=NodeKind.PASSTHROUGH,
    description="Pass-through the receipt; this is a hook point for journaling later.",
    inputs=[PortInfo("receipt", kind=PortKind.RECEIPT, required=False)],
    outputs=[PortInfo("to", kind=PortKind.RECEIPT)],
    provides=["receipt_fact"],
    consumes=["effect_receipt"],
    relates_to=["dispatch_tool", "integrate_observation"],
)
class WriteReceipt(Node):
    """Pass-through the receipt; this is a hook point for journaling later."""

    name = "write_receipt"

    def execute(self, node, inputs):
        src = node.config.get("from", "receipt")
        out_port = node.config.get("to", "receipt_fact")
        return {
            out_port: inputs[src]
            if src in inputs
            else Artifact(kind=ArtifactKind.RECEIPT, content={})
        }
