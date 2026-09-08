"""merge_messages node — combine multiple message-list artifacts into one ordered list."""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="merge_messages",
    layer=NodeLayer.MODEL_VISIBLE,
    kind=NodeKind.ASSEMBLER,
    description="Combine multiple message-list artifacts into one ordered list.",
    inputs=[PortInfo("any_in", kind=PortKind.ARTIFACT, required=False)],
    outputs=[PortInfo("messages", kind=PortKind.MESSAGE)],
    provides=["merged_messages"],
    requires=["message_list"],
    relates_to=["assemble_messages", "commit_manifest", "validate_manifest"],
)
class MergeMessages(Node):
    """Combine multiple message-list artifacts into one ordered list."""

    name = "merge_messages"

    def execute(self, node, inputs):
        out_port = node.outs[0]
        order = node.config.get("order", list(inputs.keys()))
        merged: list = []
        for k in order:
            a = inputs.get(k)
            if a is None:
                continue
            content = a.content
            if isinstance(content, list):
                merged.extend(content)
            elif isinstance(content, str):
                merged.append({"role": k, "content": content})
            else:
                merged.append({"role": k, "content": str(content)})
        return {
            out_port: Artifact(
                kind=ArtifactKind.MESSAGE,
                content=merged,
                schema_ref="openai.messages.v1",
            )
        }
