"""dedup node — collapse repeated lines / entries into a unique list."""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="dedup",
    layer=NodeLayer.MODEL_VISIBLE,
    kind=NodeKind.TRANSFORMER,
    description="Collapse repeated lines / entries into a unique list (preserves order).",
    inputs=[PortInfo("from", kind=PortKind.ARTIFACT, required=False)],
    outputs=[PortInfo("to", kind=PortKind.TEXT)],
    provides=["unique_lines"],
    relates_to=["redact", "rank", "merge_messages"],
)
class Dedup(Node):
    """Collapse repeated lines / entries into a unique list (preserves order)."""

    name = "dedup"

    def execute(self, node, inputs):
        src = node.config.get("from", node.ins[0])
        dst = node.config.get("to", node.outs[0])
        split_on = node.config.get("split_on", "\n")
        src_a = inputs.get(src)
        if src_a is None:
            return {dst: Artifact(kind=ArtifactKind.TEXT, content="")}
        text = str(src_a.content)
        parts = [p for p in text.split(split_on) if p]
        seen: set[str] = set()
        unique: list[str] = []
        for p in parts:
            if p not in seen:
                seen.add(p)
                unique.append(p)
        return {dst: Artifact(kind=ArtifactKind.TEXT, content=split_on.join(unique), schema_ref="deduped.v1")}
