"""Control nodes — join, barrier, route_on, discard.

Pure routing. No business if/else lives here — only the routing primitive.
"""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="join",
    layer=NodeLayer.CONTROL,
    kind=NodeKind.ROUTER,
    description="Wait for all required inputs, return one merged output.",
    inputs=[PortInfo("any_in", kind=PortKind.ARTIFACT, required=False)],
    outputs=[PortInfo("out", kind=PortKind.FACT)],
    provides=["joined_view"],
    relates_to=["barrier", "route_on"],
)
class Join(Node):
    """Wait for all required inputs, return one merged output."""

    name = "join"

    def execute(self, node, inputs):
        out_port = node.outs[0]
        merged: dict = {}
        for k, a in inputs.items():
            merged[k] = a.content
        return {out_port: Artifact(kind=ArtifactKind.FACT, content=merged, schema_ref="join.merged.v1")}


@node(
    id="barrier",
    layer=NodeLayer.CONTROL,
    kind=NodeKind.ROUTER,
    description="Single-slot pass-through. Real BSP barrier lives in runtime scheduler.",
    inputs=[PortInfo("from", kind=PortKind.ARTIFACT, required=False)],
    outputs=[PortInfo("to", kind=PortKind.ARTIFACT)],
    provides=["barrier_pass"],
    relates_to=["join"],
)
class Barrier(Node):
    """Single-slot pass-through. Real BSP barrier lives in runtime scheduler."""

    name = "barrier"

    def execute(self, node, inputs):
        src = node.config.get("from", node.ins[0])
        dst = node.config.get("to", node.outs[0])
        return {dst: inputs.get(src, Artifact(kind=ArtifactKind.TEXT, content=""))}


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


@node(
    id="discard",
    layer=NodeLayer.CONTROL,
    kind=NodeKind.PASSTHROUGH,
    description="Mark an artifact as discarded. Pure no-op pass-through to audit sink.",
    inputs=[PortInfo("from", kind=PortKind.ARTIFACT, required=False)],
    outputs=[PortInfo("to", kind=PortKind.FACT)],
    provides=["discard_marker"],
    relates_to=["integrate_observation"],
)
class Discard(Node):
    """Mark an artifact as discarded. Pure no-op pass-through to audit sink."""

    name = "discard"

    def execute(self, node, inputs):
        src = node.config.get("from", node.ins[0])
        out_port = node.config.get("to", node.outs[0])
        src_a = inputs.get(src)
        return {out_port: Artifact(
            kind=ArtifactKind.FACT,
            content={"discarded": True, "digest": src_a.short_id() if src_a else None},
            schema_ref="discard.v1",
        )}
