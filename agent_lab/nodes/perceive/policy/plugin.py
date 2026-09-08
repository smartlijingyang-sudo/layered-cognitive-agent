"""perceive.policy — fold GateDecided policy facts (Hub policy step)."""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="perceive.policy",
    layer=NodeLayer.PHASE,
    kind=NodeKind.TRANSFORMER,
    description="Fold prior-step GateDecided policy_fact items from Session.",
    inputs=[PortInfo("state", kind=PortKind.FACT, required=False)],
    outputs=[PortInfo("policy_items", kind=PortKind.FACT)],
    provides=["policy_items"],
    requires=["session_reader"],
    emits=["policy_items"],
    relates_to=["perceive.trim"],
)
class PerceivePolicy(Node):
    name = "perceive.policy"

    def execute(self, node, inputs):
        from agent_lab.adapters.lca_perceive import fold_policy_items

        del node
        return fold_policy_items(state_artifact=inputs.get("state"))
