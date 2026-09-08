"""think.reason — call the LLM on exposed messages (+ optional tools).

Logic lives in ``ops.py`` (node purity: plugin.py has no data branching).
"""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.nodes.think.reason.ops import complete_turn
from lca.infrastructure.llm_adapter.openai_compat import OpenAICompatAdapter


@node(
    id="think.reason",
    layer=NodeLayer.PHASE,
    kind=NodeKind.EXECUTOR,
    description=(
        "Call OpenAICompatAdapter.complete on exposed messages with optional tools; "
        "emit an LLMResponse-shaped MESSAGE artifact."
    ),
    inputs=[
        PortInfo("messages", kind=PortKind.MESSAGE),
        PortInfo("tools", kind=PortKind.FACT, required=False),
    ],
    outputs=[PortInfo("response", kind=PortKind.MESSAGE)],
    provides=["llm_response"],
    requires=["think_messages"],
    emits=["llm_call"],
    relates_to=["think.expose", "think.classify"],
)
class ThinkReason(Node):
    name = "think.reason"

    def execute(self, node, inputs):
        src = node.config.get("from", "messages")
        out = node.config.get("to", "response")
        response = complete_turn(
            inputs.get(src) or inputs.get("messages"),
            inputs.get("tools"),
            adapter_factory=OpenAICompatAdapter,
            adapter_kwargs=dict(node.config.get("adapter_kwargs", {}) or {}),
        )
        return {out: response}
