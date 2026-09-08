"""gate_enforce_node — let LCA's DecisionGate enforce or rewrite a Decision.

Calls ``DecisionGate.enforce(state, decision)`` through
``LcaThinkGateProvider`` and emits the enforced Decision plus a
``think_signal`` FACT artifact so downstream junctions can know the
think stage completed.

Provider selection is data, not code; see
    agent_lab/graphs/configs/think.yaml for the canonical call site.
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
from agent_lab.primitives.artifact import Artifact


@node(
    id="gate_enforce_node",
    name="gate_enforce_node",
    layer=NodeLayer.PHASE,
    kind=NodeKind.EXECUTOR,
    description=(
        "Run LCA DecisionGate.enforce(state, decision) and emit the "
        "enforced Decision + a think_signal so parent junctions can fire."
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
    relates_to=["parse_decision_node"],
)
class GateEnforceNode(Node):
    """Bridge Decision → enforced Decision via LcaThinkGateProvider."""

    name = "gate_enforce_node"

    def execute(self, node, inputs):
        from agent_lab.adapters.lca_think import LcaThinkGateProvider

        provider = LcaThinkGateProvider.from_node_config(node.config)
        out_port = node.config.get("to", "enforced_decision")
        result = provider.enforce(
            decision_artifact=inputs.get("decision"),
            perception_artifact=inputs.get("in_perception_signal"),
            out_port=out_port,
        )
        # The OUT port order is declared in the YAML (think.yaml's
        # `gate_enforce.outs: [enforced_decision, think_signal]`); no
        # runtime remap needed. Empty inputs get a fact artifact as a
        # last-resort fallback.
        return {port: result.get(port, Artifact(kind="fact", content=None)) for port in node.outs}
