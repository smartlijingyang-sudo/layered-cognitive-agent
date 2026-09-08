"""stop_decide_node — run StopPolicy.decide for the stop phase.

Single-node handler for the stop_decide control slot (ControlSlot.STOP_DECIDE).
Wraps LcaControlStopPolicyProvider which delegates to LCA's StopPolicy protocol.
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
    id="stop_decide_node",
    name="stop_decide_node",
    layer=NodeLayer.CONTROL,
    kind=NodeKind.EXECUTOR,
    description=(
        "Control-slot handler for stop.decide: runs StopPolicy.decide "
        "and emits a StopDecision artifact."
    ),
    inputs=[
        PortInfo("in_state", kind=PortKind.ARTIFACT, required=False),
        PortInfo("in_decision", kind=PortKind.FACT, required=False),
    ],
    outputs=[PortInfo("stop_decision", kind=PortKind.FACT)],
    provides=["control_stop_decide"],
    requires=["stop_policy"],
    emits=["stop_decision"],
)
class StopDecideNode(Node):
    """Bridge state/decision → StopDecision via LcaControlStopPolicyProvider."""

    name = "stop_decide_node"

    def execute(self, node, inputs):
        from agent_lab.adapters.lca_control import LcaControlStopPolicyProvider

        provider = LcaControlStopPolicyProvider.from_node_config(node.config)
        out_port = node.config.get("to", "stop_decision")
        return provider.decide(
            state=inputs.get("in_state"),
            decision=inputs.get("in_decision"),
            out_port=out_port,
        )
