"""think.guard — DecisionGate.enforce inside the think phase.

Gate is a Think sub-chain (ADR-0194), not a separate graph phase.
Emits enforced Decision + think_signal for the parent barrier.
"""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="think.guard",
    layer=NodeLayer.PHASE,
    kind=NodeKind.EXECUTOR,
    description=(
        "Run DecisionGate.enforce(state, decision); emit enforced Decision and think_signal."
    ),
    inputs=[
        PortInfo("decision", kind=PortKind.FACT, required=False),
        PortInfo("in_perception_signal", kind=PortKind.ARTIFACT, required=False),
    ],
    outputs=[
        PortInfo("enforced_decision", kind=PortKind.FACT),
        PortInfo("think_signal", kind=PortKind.FACT),
    ],
    provides=["decision_gate_enforced", "think_signal"],
    requires=["decision_gate"],
    emits=["enforced_decision"],
    relates_to=["think.classify"],
)
class ThinkGuard(Node):
    name = "think.guard"

    def execute(self, node, inputs):
        from agent_lab.adapters.lca_think import LcaThinkGateProvider

        provider = LcaThinkGateProvider.from_node_config(node.config)
        src = node.config.get("from", "decision")
        out = node.config.get("to", "enforced_decision")
        result = provider.enforce(
            decision_artifact=inputs.get(src) or inputs.get("decision"),
            perception_artifact=inputs.get("in_perception_signal"),
            out_port=out,
        )
        # Preserve declared outs; fill missing ports fail-soft with empty fact.
        return {
            port: result.get(port, Artifact(kind=ArtifactKind.FACT, content=None))
            for port in (node.outs or [out, "think_signal"])
        }
