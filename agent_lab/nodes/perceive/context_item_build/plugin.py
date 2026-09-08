"""perceive__context_item_build — 1 in 1 out: user_turn -> ContextItem (stub).

Real implementation (post-skeleton) calls Hub.add_user_turn().
"""
from __future__ import annotations
from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="perceive__context_item_build",
    layer=NodeLayer.MODEL_VISIBLE,
    kind=NodeKind.PRODUCER,
    description="Wrap user_turn artifact as a ContextItem (stub: passthrough).",
    inputs=[PortInfo("user_turn", kind=PortKind.MESSAGE)],
    outputs=[PortInfo("context_item", kind=PortKind.FACT)],
)
class ContextItemBuild(Node):
    name = "perceive__context_item_build"

    def execute(self, node, inputs):
        return {"context_item": inputs.get("user_turn")}
