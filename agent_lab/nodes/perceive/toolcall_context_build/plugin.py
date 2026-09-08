"""perceive__toolcall_context_build — 1 in 1 out: tool_calls/results -> ContextItem (stub).

Real implementation pulls {role:tool} messages out of the upstream history
fold and wraps them as ContextItems for the next Hub.perceive call.
"""
from __future__ import annotations
from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="perceive__toolcall_context_build",
    layer=NodeLayer.MODEL_VISIBLE,
    kind=NodeKind.TRANSFORMER,
    description="Convert upstream tool-role messages into ContextItem list (stub).",
    inputs=[PortInfo("history", kind=PortKind.MESSAGE)],
    outputs=[PortInfo("context_items", kind=PortKind.FACT)],
)
class ToolcallContextBuild(Node):
    name = "perceive__toolcall_context_build"

    def execute(self, node, inputs):
        return {"context_items": inputs.get("history")}
