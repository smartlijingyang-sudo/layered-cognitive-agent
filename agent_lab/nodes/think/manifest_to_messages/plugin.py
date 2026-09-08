"""think__manifest_to_messages — 1 in 1 out: ContextManifest -> messages list."""
from __future__ import annotations
from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="think__manifest_to_messages",
    layer=NodeLayer.PHASE,
    kind=NodeKind.TRANSFORMER,
    description="Extract messages field from frozen ContextManifest (stub: passthrough).",
    inputs=[PortInfo("manifest", kind=PortKind.MANIFEST)],
    outputs=[PortInfo("messages", kind=PortKind.MESSAGE)],
)
class ManifestToMessages(Node):
    name = "think__manifest_to_messages"

    def execute(self, node, inputs):
        return {"messages": inputs.get("manifest")}
