"""rank node — keep top-K entries by line order (no scoring; just truncate)."""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="rank",
    layer=NodeLayer.MODEL_VISIBLE,
    kind=NodeKind.TRANSFORMER,
    description="Keep top-K entries (no scoring; just truncate).",
    inputs=[PortInfo("from", kind=PortKind.ARTIFACT, required=False)],
    outputs=[PortInfo("to", kind=PortKind.TEXT)],
    provides=["top_k_text"],
    relates_to=["dedup", "redact", "merge_messages"],
)
class Rank(Node):
    """Keep top-K entries (no scoring; just truncate)."""

    name = "rank"

    def execute(self, node, inputs):
        src = node.config.get("from", node.ins[0])
        dst = node.config.get("to", node.outs[0])
        keep = int(node.config.get("keep", 50))
        split_on = node.config.get("split_on", "\n")
        src_a = inputs.get(src)
        if src_a is None:
            return {dst: Artifact(kind=ArtifactKind.TEXT, content="")}
        text = str(src_a.content)
        parts = [p for p in text.split(split_on) if p][:keep]
        return {dst: Artifact(kind=ArtifactKind.TEXT, content=split_on.join(parts), schema_ref="ranked.v1")}
