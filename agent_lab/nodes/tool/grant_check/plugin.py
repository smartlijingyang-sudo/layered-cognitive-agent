"""grant_check node — static allowlist check (config.allow:[str]). No business logic."""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="grant_check",
    layer=NodeLayer.EFFECT,
    kind=NodeKind.VALIDATOR,
    description="Static allowlist check (config.allow:[str]). No business logic.",
    inputs=[PortInfo("intent", kind=PortKind.INTENT, required=False)],
    outputs=[PortInfo("verdict", kind=PortKind.VERDICT)],
    provides=["grant_verdict"],
    consumes=["tool_intent"],
    relates_to=["build_intent", "dispatch_tool", "route_on"],
)
class GrantCheck(Node):
    """Static allowlist check (config.allow:[str]). No business logic."""

    name = "grant_check"

    def execute(self, node, inputs):
        allow = set(node.config.get("allow", []))
        intent_a = inputs.get("intent")
        out_port = node.config.get("to", "verdict")
        tool = intent_a.content.get("tool") if intent_a else None
        verdict = "allow" if tool in allow else "deny"
        return {out_port: Artifact(kind=ArtifactKind.FACT, content={"verdict": verdict, "tool": tool}, schema_ref="grant.verdict.v1")}
