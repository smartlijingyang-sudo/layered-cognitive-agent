"""act__receipt_to_text — 1 in 1 out: EffectReceipt -> model-visible observation text."""
from __future__ import annotations
from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="act__receipt_to_text",
    layer=NodeLayer.EFFECT,
    kind=NodeKind.TRANSFORMER,
    description="Render EffectReceipt into observation text (success/error template).",
    inputs=[PortInfo("receipt", kind=PortKind.RECEIPT)],
    outputs=[PortInfo("observation", kind=PortKind.MANIFEST)],
)
class ReceiptToText(Node):
    name = "act__receipt_to_text"

    def execute(self, node, inputs):
        return {"observation": inputs.get("receipt")}
