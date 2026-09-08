"""build_intent node — package (tool_name, args) into a structured ToolIntent artifact."""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="build_intent",
    layer=NodeLayer.EFFECT,
    kind=NodeKind.PRODUCER,
    description="Combine tool name (config) + args into a structured ToolIntent artifact.",
    inputs=[PortInfo("args", kind=PortKind.FACT, required=False)],
    outputs=[PortInfo("intent", kind=PortKind.INTENT)],
    provides=["tool_intent"],
    consumes=[],
    emits=["tool_intent"],
    relates_to=["grant_check", "dispatch_tool"],
)
class BuildIntent(Node):
    """Combine model intent (text) + context into a structured ToolIntent artifact."""

    name = "build_intent"

    def execute(self, node, inputs):
        out_port = node.config.get("to", "intent")
        args_a = inputs.get("args")
        raw = args_a.content if args_a else {}
        if not isinstance(raw, dict):
            raw = {}
        # args may be either:
        #   a) {"tool": "<name>", "args": {<tool args>}}  (preferred)
        #   b) {<tool args>}  when the caller already knows the tool name
        #      (then config.tool is the default)
        if "tool" in raw and isinstance(raw["tool"], str):
            tool_name = raw["tool"]
            tool_args = raw.get("args", {}) or {}
        else:
            tool_name = node.config["tool"]
            tool_args = raw
        return {out_port: Artifact(
            kind=ArtifactKind.INTENT,
            content={"tool": tool_name, "args": tool_args},
            schema_ref="tool.intent.v1",
        )}
