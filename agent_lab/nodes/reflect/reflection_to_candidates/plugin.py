"""reflect__reflection_to_candidates — 1 in 1 out: Reflection -> memory candidates list."""
from __future__ import annotations
from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="reflect__reflection_to_candidates",
    layer=NodeLayer.PHASE,
    kind=NodeKind.TRANSFORMER,
    description="Extract memory candidates (lesson / correction / extra) from Reflection.",
    inputs=[PortInfo("reflection", kind=PortKind.MANIFEST)],
    outputs=[PortInfo("candidates", kind=PortKind.FACT)],
)
class ReflectionToCandidates(Node):
    name = "reflect__reflection_to_candidates"

    def execute(self, node, inputs):
        return {"candidates": inputs.get("reflection")}
