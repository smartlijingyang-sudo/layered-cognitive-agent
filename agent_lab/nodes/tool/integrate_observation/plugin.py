"""integrate_observation node — convert a receipt into a model-visible observation artifact."""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="integrate_observation",
    layer=NodeLayer.EFFECT,
    kind=NodeKind.TRANSFORMER,
    description="Convert a receipt into a model-visible observation artifact.",
    inputs=[PortInfo("receipt_fact", kind=PortKind.RECEIPT, required=False)],
    outputs=[PortInfo("observation", kind=PortKind.TEXT)],
    provides=["observation"],
    consumes=["effect_receipt"],
    relates_to=["dispatch_tool", "write_receipt", "merge_messages"],
)
class IntegrateObservation(Node):
    """Convert a receipt into a model-visible observation artifact."""

    name = "integrate_observation"

    def execute(self, node, inputs):
        src = node.config.get("from", "receipt")
        out_port = node.config.get("to", "observation")
        rcpt = inputs.get(src)
        if rcpt is None:
            return {out_port: Artifact(kind=ArtifactKind.TEXT, content="")}
        text = ""
        if rcpt.content.get("status") == "ok":
            text = f"[tool:{rcpt.content.get('tool')}] {rcpt.content.get('result', '')}"
        else:
            text = f"[tool-error] {rcpt.content.get('error') or rcpt.content.get('status')}"
        return {out_port: Artifact(kind=ArtifactKind.TEXT, content=text, schema_ref="observation.v1")}
