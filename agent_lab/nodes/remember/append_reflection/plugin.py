"""remember__append_reflection — 1 in 1 out: Reflection -> session_event(seq) (stub)."""
from __future__ import annotations
from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="remember__append_reflection",
    layer=NodeLayer.PHASE,
    kind=NodeKind.EXECUTOR,
    description="Append Reflection to Session — stub.",
    inputs=[PortInfo("reflection", kind=PortKind.MANIFEST)],
    outputs=[PortInfo("seq", kind=PortKind.FACT)],
)
class AppendReflection(Node):
    name = "remember__append_reflection"

    def execute(self, node, inputs):
        return {"seq": inputs.get("reflection")}
