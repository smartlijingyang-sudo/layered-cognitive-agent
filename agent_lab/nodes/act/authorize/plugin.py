"""act.authorize — Intent → stamped Intent with grant verdict.

Static allowlist from ``config.allow``. no_effect intents are skipped
(verdict=skip) so execute never touches the world. Does not execute.
"""

from __future__ import annotations

from typing import Any

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="act.authorize",
    layer=NodeLayer.EFFECT,
    kind=NodeKind.VALIDATOR,
    description=(
        "Stamp Intent with verdict ∈ {allow, deny, skip}. "
        "no_effect → skip; call_tool checked against config.allow."
    ),
    inputs=[PortInfo("intent", kind=PortKind.INTENT, required=False)],
    outputs=[PortInfo("authorized", kind=PortKind.INTENT)],
    provides=["grant_verdict"],
    consumes=["tool_intent"],
    relates_to=["act.shape", "act.execute"],
)
class ActAuthorize(Node):
    """Allowlist grant check; stamps verdict onto the Intent."""

    name = "act.authorize"

    def execute(self, node, inputs):
        out_port = node.config.get("to", "authorized")
        intent_a = inputs.get(node.config.get("from", "intent"))
        content = _content(intent_a)
        allow = set(node.config.get("allow", []) or [])

        effect_kind = content.get("effect_kind") or "call_tool"
        tool = content.get("tool")

        if effect_kind == "no_effect" or tool in (None, "__none__"):
            verdict = "skip"
        elif tool in allow:
            verdict = "allow"
        else:
            verdict = "deny"

        stamped = {
            **content,
            "verdict": verdict,
            "tool": tool,
        }
        return {
            out_port: Artifact(
                kind=ArtifactKind.INTENT,
                content=stamped,
                schema_ref="tool.intent.v1",
            )
        }


def _content(artifact: Any) -> dict[str, Any]:
    if artifact is None:
        return {}
    raw = getattr(artifact, "content", None)
    return raw if isinstance(raw, dict) else {}
