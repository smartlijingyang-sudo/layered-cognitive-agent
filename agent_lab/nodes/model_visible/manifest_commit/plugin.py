"""model_visible__manifest_commit — 1 in 1 out: messages list -> frozen ContextManifest."""
from __future__ import annotations
from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="model_visible__manifest_commit",
    layer=NodeLayer.MODEL_VISIBLE,
    kind=NodeKind.PRODUCER,
    description="Wrap messages list into a frozen ContextManifest (no LCA dependency).",
    inputs=[PortInfo("messages", kind=PortKind.MESSAGE)],
    outputs=[PortInfo("manifest", kind=PortKind.MANIFEST)],
)
class ManifestCommit(Node):
    name = "model_visible__manifest_commit"

    def execute(self, node, inputs):
        msgs_a = inputs.get("messages")
        return {"manifest": msgs_a}
