"""think.expose — peel messages from a frozen ContextManifest.

Logic lives in ``ops.py`` (node purity: plugin.py has no data branching).
"""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.nodes.think.expose.ops import peel_messages


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
        messages = peel_messages(inputs.get(src) or inputs.get("in_assembled_manifest"))
        return {out: messages}
