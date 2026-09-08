"""think.expose — peel messages + tools from a frozen ContextManifest.

Logic lives in ``ops.py`` (node purity: plugin.py has no data branching).
"""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.nodes.think.expose.ops import peel_manifest


@node(
    id="think.expose",
    layer=NodeLayer.PHASE,
    kind=NodeKind.TRANSFORMER,
    description=(
        "Extract messages and tools from a committed ContextManifest. "
        "Fail-loud when committed is false or messages are missing."
    ),
    inputs=[PortInfo("in_assembled_manifest", kind=PortKind.MANIFEST)],
    outputs=[
        PortInfo("messages", kind=PortKind.MESSAGE),
        PortInfo("tools", kind=PortKind.FACT),
    ],
    provides=["think_messages", "think_tools"],
    requires=["context_manifest"],
    relates_to=["think.reason", "model_eye.freeze"],
)
class ThinkExpose(Node):
    name = "think.expose"

    def execute(self, node, inputs):
        src = node.config.get("from", "in_assembled_manifest")
        peeled = peel_manifest(inputs.get(src) or inputs.get("in_assembled_manifest"))
        msg_out = node.config.get("to", "messages")
        tools_out = node.config.get("tools_to", "tools")
        return {
            msg_out: peeled["messages"],
            tools_out: peeled["tools"],
        }
