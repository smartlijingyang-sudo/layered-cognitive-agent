"""route_on node — pick one input port per output based on config.table."""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="route_on",
    layer=NodeLayer.CONTROL,
    kind=NodeKind.ROUTER,
    description="Pick one input port per output based on config.table.",
    inputs=[PortInfo("key_from", kind=PortKind.VERDICT, required=False)],
    outputs=[PortInfo("routed", kind=PortKind.FACT)],
    provides=["conditional_route"],
    relates_to=["grant_check", "dispatch_tool"],
)
class RouteOn(Node):
    """Pick one input port per output based on config.table."""

    name = "route_on"

    def execute(self, node, inputs):
        key_in = node.config["key_from"]
        table: dict[str, str] = node.config["table"]
        out_port = node.outs[0]
        key_a = inputs.get(key_in)
        if key_a is None:
            return {out_port: Artifact(kind=ArtifactKind.FACT, content={"routed": None})}
        key = str(key_a.content) if not isinstance(key_a.content, dict) else str(key_a.content.get("verdict", ""))
        chosen_in = table.get(key, node.config.get("default"))
        if chosen_in is None or chosen_in not in inputs:
            return {out_port: Artifact(
                kind=ArtifactKind.INTENT,
                content={"tool": "__none__", "args": {}, "verdict": "deny"},
                schema_ref="tool.intent.v1",
            )}
        chosen = inputs[chosen_in]
        return {out_port: chosen.model_copy(update={"content": {**chosen.content, "routed_via": key}})}
