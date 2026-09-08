"""perceive.sense.memory.normalize — coerce raw items to ContextItem dicts.

Single-responsibility: list[MemoryRecord|dict] → list[dict] with stable
keys (kind/payload/provenance/ref/extra). Mirrors LCA ContextItem shape
so downstream perceive_aggregate + Hub consume a uniform artifact.
"""
from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="perceive.sense.memory.normalize",
    layer=NodeLayer.MODEL_VISIBLE,
    kind=NodeKind.TRANSFORMER,
    description="Normalize raw memory items to list[dict] ContextItem shape (kind/payload/provenance/ref/extra).",
    inputs=[PortInfo("raw_items", kind=PortKind.ARTIFACT)],
    outputs=[PortInfo("retrieved_context", kind=PortKind.ARTIFACT)],
)
class NormalizeMemory(Node):
    name = "perceive.sense.memory.normalize"

    def execute(self, node, inputs):
        ri_a = inputs.get("raw_items")
        raw = ri_a.content if ri_a is not None and isinstance(ri_a.content, list) else []
        items = [_coerce(it) for it in raw]
        return {"retrieved_context": Artifact(
            kind=ArtifactKind.FACT,
            content=items,
            schema_ref="context.items.v1",
        )}


def _coerce(it):
    if isinstance(it, dict):
        return it
    return {
        "kind": getattr(it, "kind", ""),
        "payload": getattr(it, "payload", None),
        "provenance": getattr(it, "provenance", ""),
        "ref": getattr(it, "ref", None),
        "extra": dict(getattr(it, "extra", {}) or {}),
    }
