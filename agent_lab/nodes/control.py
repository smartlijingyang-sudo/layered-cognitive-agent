"""Control nodes — join, barrier, route_on, discard.

Pure routing. No business if/else lives here — only the routing primitive.
"""

from __future__ import annotations

from agent_lab.graph.spec import InfoNode
from agent_lab.nodes.base import Node, register
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@register
class Join(Node):
    """Wait for all required inputs, return one merged output."""

    name = "join"

    def execute(self, node: InfoNode, inputs: dict[str, Artifact]) -> dict[str, Artifact]:
        out_port = node.outs[0]
        merged: dict = {}
        for k, a in inputs.items():
            merged[k] = a.content
        return {out_port: Artifact(kind=ArtifactKind.FACT, content=merged, schema_ref="join.merged.v1")}


@register
class Barrier(Node):
    """Single-slot pass-through. Real BSP barrier lives in runtime scheduler."""

    name = "barrier"

    def execute(self, node: InfoNode, inputs: dict[str, Artifact]) -> dict[str, Artifact]:
        src = node.config.get("from", node.ins[0])
        dst = node.config.get("to", node.outs[0])
        return {dst: inputs.get(src, Artifact(kind=ArtifactKind.TEXT, content=""))}


@register
class RouteOn(Node):
    """Pick one input port per output based on config.table."""

    name = "route_on"

    def execute(self, node: InfoNode, inputs: dict[str, Artifact]) -> dict[str, Artifact]:
        key_in = node.config["key_from"]
        table: dict[str, str] = node.config["table"]   # value -> input port name
        out_port = node.outs[0]
        key_a = inputs.get(key_in)
        if key_a is None:
            return {out_port: Artifact(kind=ArtifactKind.FACT, content={"routed": None})}
        key = str(key_a.content) if not isinstance(key_a.content, dict) else str(key_a.content.get("verdict", ""))
        chosen_in = table.get(key, node.config.get("default"))
        if chosen_in is None or chosen_in not in inputs:
            # Pass through a deny marker
            return {out_port: Artifact(
                kind=ArtifactKind.INTENT,
                content={"tool": "__none__", "args": {}, "verdict": "deny"},
                schema_ref="tool.intent.v1",
            )}
        chosen = inputs[chosen_in]
        # Reuse the chosen artifact directly so downstream sees the right kind/content
        return {out_port: chosen.model_copy(update={"content": {**chosen.content, "routed_via": key}})}


@register
class Discard(Node):
    """Mark an artifact as discarded. Pure no-op pass-through to audit sink."""

    name = "discard"

    def execute(self, node: InfoNode, inputs: dict[str, Artifact]) -> dict[str, Artifact]:
        src = node.config.get("from", node.ins[0])
        out_port = node.config.get("to", node.outs[0])
        src_a = inputs.get(src)
        return {out_port: Artifact(
            kind=ArtifactKind.FACT,
            content={"discarded": True, "digest": src_a.short_id() if src_a else None},
            schema_ref="discard.v1",
        )}
