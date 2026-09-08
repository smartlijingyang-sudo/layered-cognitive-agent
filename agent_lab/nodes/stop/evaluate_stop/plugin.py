"""evaluate_stop_node — call StopPolicy.decide() to produce a StopDecision.

Reads four artifacts (in_decision, in_observation, in_reflection, in_state),
calls ``StopPolicy.decide(state, decision, observation, reflection)`` through
``LcaStopPolicyProvider``, and emits stop_decision + terminal FACT artifacts.

Provider selection is data, not code; see
    agent_lab/graphs/configs/stop.yaml for the canonical call site.
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
    id="evaluate_stop_node",
    name="evaluate_stop_node",
    layer=NodeLayer.PHASE,
    kind=NodeKind.EXECUTOR,
    description=(
        "Call LCA StopPolicy.decide(state, decision, observation, reflection) "
        "and emit a StopDecision + terminal fact artifact."
    ),
    inputs=[
        PortInfo("in_decision", kind=PortKind.FACT, required=False),
        PortInfo("in_observation", kind=PortKind.FACT, required=False),
        PortInfo("in_reflection", kind=PortKind.FACT, required=False),
        PortInfo("in_state", kind=PortKind.FACT, required=False),
    ],
    outputs=[
        PortInfo("stop_decision", kind=PortKind.FACT),
        PortInfo("terminal", kind=PortKind.FACT),
    ],
    provides=["stop_decision", "terminal"],
    requires=["stop_policy"],
    emits=["stop_decision"],
    relates_to=[],
)
class EvaluateStopNode(Node):
    """Bridge evaluate_stop node → LCA StopPolicy via LcaStopPolicyProvider."""

    name = "evaluate_stop_node"

    def execute(self, node, inputs):
        from agent_lab.adapters.lca_stop import LcaStopPolicyProvider

        provider = LcaStopPolicyProvider.from_node_config(node.config)
        return provider.decide(
            state_artifact=inputs.get("in_state"),
            decision_artifact=inputs.get("in_decision"),
            observation_artifact=inputs.get("in_observation"),
            reflection_artifact=inputs.get("in_reflection"),
        )
