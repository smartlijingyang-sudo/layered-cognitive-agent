"""perceive.sense.memory.query — query the resolved MemorySystem.

Single-responsibility: MemorySystem + (no extra inputs) → list of raw
items (MemoryRecord objects or dicts). Errors are swallowed into empty
list (memory is best-effort context, not a hard dependency).
"""
from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="perceive.sense.memory.query",
    layer=NodeLayer.MODEL_VISIBLE,
    kind=NodeKind.TRANSFORMER,
    description="Query MemorySystem at MemoryLayer.WORKING; return raw items (list of MemoryRecord or dict).",
    inputs=[PortInfo("memory_system", kind=PortKind.ARTIFACT)],
    outputs=[PortInfo("raw_items", kind=PortKind.ARTIFACT)],
)
class QueryMemory(Node):
    name = "perceive.sense.memory.query"

    def execute(self, node, inputs):
        from lca.contracts.atoms.enums.enums import MemoryLayer

        ms_a = inputs.get("memory_system")
        mem_sys = ms_a.content if ms_a is not None else None
        if mem_sys is None:
            return {"raw_items": Artifact(
                kind=ArtifactKind.FACT,
                content=[],
                schema_ref="memory.items.v1",
            )}
        try:
            raw = mem_sys.query(MemoryLayer.WORKING) if hasattr(mem_sys, "query") else []
        except Exception:
            raw = []
        return {"raw_items": Artifact(
            kind=ArtifactKind.FACT,
            content=list(raw or []),
            schema_ref="memory.items.v1",
        )}
