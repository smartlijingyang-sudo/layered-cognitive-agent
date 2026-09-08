"""perceive_context_node — evaluate perceive.context control slot.

Single-purpose worker that delegates to LcaControlPerceiveContextProvider.
Reads in_args, emits {allowed: bool} as a FACT artifact.
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
    id="perceive_context_node",
    name="perceive_context_node",
    layer=NodeLayer.CONTROL,
    kind=NodeKind.VALIDATOR,
    description=(
        "Evaluate the perceive.context control slot. Wraps a callable "
        "that decides whether external data becomes trusted context."
    ),
    inputs=[PortInfo("in_args", kind=PortKind.ARTIFACT, required=False)],
    outputs=[PortInfo("allowed", kind=PortKind.FACT)],
    provides=["perceive_context_slot"],
    requires=[],
    relates_to=[],
)
class PerceiveContextNode(Node):
    """Bridge to LcaControlPerceiveContextProvider."""

    name = "perceive_context_node"

    def execute(self, node, inputs):
        from agent_lab.adapters.lca_control_act import LcaControlPerceiveContextProvider

        provider = LcaControlPerceiveContextProvider.from_node_config(node.config)
        out_port = node.config.get("to", "allowed")
        result = provider.evaluate(inputs.get("in_args"))
        return {out_port: result.get(out_port, Artifact(kind="fact", content={"allowed": True}))}
