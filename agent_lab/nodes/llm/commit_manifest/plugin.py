"""commit_manifest node — wrap final messages into a frozen ContextManifest."""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="commit_manifest",
    layer=NodeLayer.MODEL_VISIBLE,
    kind=NodeKind.PRODUCER,
    description="Wrap final messages into a frozen ContextManifest.",
    inputs=[PortInfo("from", kind=PortKind.MESSAGE, required=False)],
    outputs=[PortInfo("to", kind=PortKind.MANIFEST)],
    provides=["context_manifest"],
    requires=["message_list"],
    relates_to=["assemble_messages", "validate_manifest"],
)
class CommitManifest(Node):
    """Wrap final messages into a frozen ContextManifest."""

    name = "commit_manifest"

    def execute(self, node, inputs):
        src = node.config.get("from", "messages")
        out_port = node.config.get("to", "manifest")
        src_a = inputs.get(src)
        messages = src_a.content if src_a else []
        return {
            out_port: Artifact(
                kind=ArtifactKind.MANIFEST,
                content={"messages": messages, "committed": True},
                schema_ref="context.manifest.v1",
            )
        }
