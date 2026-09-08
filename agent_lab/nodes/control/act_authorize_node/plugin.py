"""act_authorize_node — evaluate act.authorize control slot.

Single-purpose worker that delegates to LcaControlActAuthorizeProvider.
Reads in_args (tool name + arguments), emits {allowed: bool} as a FACT.
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
    id="act_authorize_node",
    name="act_authorize_node",
    layer=NodeLayer.CONTROL,
    kind=NodeKind.VALIDATOR,
    description=(
        "Evaluate the act.authorize control slot. Wraps a callable or "
        "allowlist that authorizes tool execution."
    ),
    inputs=[PortInfo("in_args", kind=PortKind.ARTIFACT, required=False)],
    outputs=[PortInfo("allowed", kind=PortKind.FACT)],
    provides=["act_authorize_slot"],
    requires=[],
    relates_to=[],
)
class ActAuthorizeNode(Node):
    """Bridge to LcaControlActAuthorizeProvider."""

    name = "act_authorize_node"

    def execute(self, node, inputs):
        from agent_lab.adapters.lca_control_act import LcaControlActAuthorizeProvider

        provider = LcaControlActAuthorizeProvider.from_node_config(node.config)
        out_port = node.config.get("to", "allowed")
        result = provider.evaluate(inputs.get("in_args"))
        return {out_port: result.get(out_port, Artifact(kind="fact", content={"allowed": True}))}
