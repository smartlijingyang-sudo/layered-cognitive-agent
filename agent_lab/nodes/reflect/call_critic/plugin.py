"""call_critic — invoke Critic.critique(state, observation) → Reflection.

Calls through ``LcaReflectCriticProvider`` so provider selection is data,
not code.  The adapter resolves fixture / factory / fallback at runtime.
"""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import (
    NodeKind,
    NodeLayer,
    PortInfo,
    PortKind,
    node,
)


@node(
    id="call_critic",
    name="call_critic",
    layer=NodeLayer.PHASE,
    kind=NodeKind.EXECUTOR,
    description=(
        "Call LCA Critic.critique(state, observation) via "
        "LcaReflectCriticProvider and emit a Reflection artifact."
    ),
    inputs=[
        PortInfo("combined", kind=PortKind.FACT, required=False),
    ],
    outputs=[PortInfo("reflection", kind=PortKind.FACT)],
    provides=["reflection"],
    requires=["critic"],
    emits=["reflection"],
    relates_to=["gather_inputs", "extract_memory"],
)
class CallCriticNode(Node):
    """Bridge combined artifact → Reflection via LcaReflectCriticProvider."""

    name = "call_critic"

    def execute(self, node, inputs):
        from agent_lab.adapters.lca_reflect import LcaReflectCriticProvider

        provider = LcaReflectCriticProvider.from_node_config(node.config)
        combined = inputs.get("combined")
        return provider.critique(combined_artifact=combined)
