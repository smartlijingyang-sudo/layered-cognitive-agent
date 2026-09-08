"""think_guard_node — run a DecisionGate.enforce on an inbound decision.

Single-node handler for the think_guard control slot (ControlSlot.THINK_GUARD).
Wraps LcaControlDecisionGateProvider which delegates to LCA's DecisionGate
protocol.
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
    id="think_guard_node",
    name="think_guard_node",
    layer=NodeLayer.CONTROL,
    kind=NodeKind.EXECUTOR,
    description=(
        "Control-slot handler for think.guard: runs DecisionGate.enforce "
        "on the inbound decision and emits the guarded decision."
    ),
    inputs=[PortInfo("in_decision", kind=PortKind.FACT, required=False)],
    outputs=[PortInfo("out_decision", kind=PortKind.FACT)],
    provides=["control_think_guard"],
    requires=["decision_gate"],
    emits=["guarded_decision"],
)
class ThinkGuardNode(Node):
    """Bridge inbound decision → guarded decision via LcaControlDecisionGateProvider."""

    name = "think_guard_node"

    def execute(self, node, inputs):
        from agent_lab.adapters.lca_control import LcaControlDecisionGateProvider

        provider = LcaControlDecisionGateProvider.from_node_config(node.config)
        out_port = node.config.get("to", "out_decision")
        return provider.enforce(
            decision_artifact=inputs.get("in_decision"),
            out_port=out_port,
        )
