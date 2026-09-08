"""think.expose — peel messages from a frozen ContextManifest.

Contract seam only: does not assemble, redact, or re-order context.
model_eye already froze what the model may see; think only reads it.
"""

from __future__ import annotations

from typing import Any

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="think.expose",
    layer=NodeLayer.PHASE,
    kind=NodeKind.TRANSFORMER,
    description=(
        "Extract messages from a committed ContextManifest. "
        "Fail-loud when committed is false or messages are missing."
    ),
    inputs=[PortInfo("in_assembled_manifest", kind=PortKind.MANIFEST)],
    outputs=[PortInfo("messages", kind=PortKind.MESSAGE)],
    provides=["think_messages"],
    requires=["context_manifest"],
    relates_to=["think.reason", "model_eye.freeze"],
)
class ThinkExpose(Node):
    name = "think.expose"

    def execute(self, node, inputs):
        src = node.config.get("from", "in_assembled_manifest")
        out = node.config.get("to", "messages")
        src_a = inputs.get(src) or inputs.get("in_assembled_manifest")
        if src_a is None:
            raise ValueError("think.expose: missing ContextManifest input")

        content = src_a.content
        if not isinstance(content, dict):
            raise ValueError(
                f"think.expose: ContextManifest content must be dict, got {type(content).__name__}"
            )
        if content.get("committed") is not True:
            raise ValueError(
                "think.expose: ContextManifest is not committed; "
                "refuse to feed an unfrozen view to reason"
            )
        raw_messages = content.get("messages")
        if not isinstance(raw_messages, list):
            raise ValueError("think.expose: ContextManifest.messages missing or not a list")

        messages: list[dict[str, Any]] = [dict(m) for m in raw_messages if isinstance(m, dict)]
        return {
            out: Artifact(
                kind=ArtifactKind.MESSAGE,
                content=messages,
                schema_ref="openai.messages.v1",
            )
        }
