"""act_budget_node — evaluate act.budget control slot.

Single-purpose worker that delegates to LcaControlActBudgetProvider.
Reads in_state (AgentState) + in_args, emits {allowed: bool} as a FACT.
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
    id="act_budget_node",
    name="act_budget_node",
    layer=NodeLayer.CONTROL,
    kind=NodeKind.VALIDATOR,
    description=(
        "Evaluate the act.budget control slot. Wraps a BudgetPolicy that "
        "checks whether the current action stays within budget."
    ),
    inputs=[
        PortInfo("in_args", kind=PortKind.ARTIFACT, required=False),
        PortInfo("in_state", kind=PortKind.ARTIFACT, required=False),
    ],
    outputs=[PortInfo("allowed", kind=PortKind.FACT)],
    provides=["act_budget_slot"],
    requires=[],
    relates_to=[],
)
class ActBudgetNode(Node):
    """Bridge to LcaControlActBudgetProvider."""

    name = "act_budget_node"

    def execute(self, node, inputs):
        from agent_lab.adapters.lca_control_act import LcaControlActBudgetProvider

        provider = LcaControlActBudgetProvider.from_node_config(node.config)
        out_port = node.config.get("to", "allowed")
        result = provider.evaluate(
            state_artifact=inputs.get("in_state"),
            args_artifact=inputs.get("in_args"),
        )
        return {out_port: result.get(out_port, Artifact(kind="fact", content={"allowed": True}))}
