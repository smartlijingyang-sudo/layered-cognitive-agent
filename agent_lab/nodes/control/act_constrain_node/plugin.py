"""act_constrain_node — evaluate act.constrain control slot.

Single-purpose worker that delegates to LcaControlActConstrainProvider.
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
    id="act_constrain_node",
    name="act_constrain_node",
    layer=NodeLayer.CONTROL,
    kind=NodeKind.VALIDATOR,
    description=(
        "Evaluate the act.constrain control slot. Wraps a callable that "
        "applies strategy constraints before execution."
    ),
    inputs=[PortInfo("in_args", kind=PortKind.ARTIFACT, required=False)],
    outputs=[PortInfo("allowed", kind=PortKind.FACT)],
    provides=["act_constrain_slot"],
    requires=[],
    relates_to=[],
)
class ActConstrainNode(Node):
    """Bridge to LcaControlActConstrainProvider."""

    name = "act_constrain_node"

    def execute(self, node, inputs):
        from agent_lab.adapters.lca_control_act import LcaControlActConstrainProvider

        provider = LcaControlActConstrainProvider.from_node_config(node.config)
        out_port = node.config.get("to", "allowed")
        result = provider.evaluate(inputs.get("in_args"))
        return {out_port: result.get(out_port, Artifact(kind="fact", content={"allowed": True}))}
