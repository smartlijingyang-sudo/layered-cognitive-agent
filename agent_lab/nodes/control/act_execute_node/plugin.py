"""act_execute_node — evaluate act.execute control slot.

Single-purpose worker that delegates to LcaControlActExecuteProvider.
Reads in_args, emits {allowed: bool} as a FACT.
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
    id="act_execute_node",
    name="act_execute_node",
    layer=NodeLayer.CONTROL,
    kind=NodeKind.VALIDATOR,
    description=(
        "Evaluate the act.execute control slot. Wraps a callable that "
        "gates safe execution of the authorized action."
    ),
    inputs=[PortInfo("in_args", kind=PortKind.ARTIFACT, required=False)],
    outputs=[PortInfo("allowed", kind=PortKind.FACT)],
    provides=["act_execute_slot"],
    requires=[],
    relates_to=[],
)
class ActExecuteNode(Node):
    """Bridge to LcaControlActExecuteProvider."""

    name = "act_execute_node"

    def execute(self, node, inputs):
        from agent_lab.adapters.lca_control_act import LcaControlActExecuteProvider

        provider = LcaControlActExecuteProvider.from_node_config(node.config)
        out_port = node.config.get("to", "allowed")
        result = provider.evaluate(inputs.get("in_args"))
        return {out_port: result.get(out_port, Artifact(kind="fact", content={"allowed": True}))}
