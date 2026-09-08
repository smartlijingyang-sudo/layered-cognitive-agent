"""act.authorize — Intent → stamped Intent with grant verdict.

- use_tool: config.allow tool allowlist
- respond / stop / ask_human: allow (Body ActionRegistry is the authority)
- no_effect / malformed: skip
"""

from __future__ import annotations

from typing import Any

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind

_BODY_NON_TOOL = frozenset({"respond", "stop", "ask_human", "delegate", "handoff"})
_TOOL_KINDS = frozenset({"use_tool", "call_tool"})


@node(
    id="act.authorize",
    layer=NodeLayer.EFFECT,
    kind=NodeKind.VALIDATOR,
    description=(
        "Stamp Intent with verdict ∈ {allow, deny, skip}. "
        "use_tool checked against config.allow; respond/stop/ask_human always allow."
    ),
    inputs=[PortInfo("intent", kind=PortKind.INTENT, required=False)],
    outputs=[PortInfo("authorized", kind=PortKind.INTENT)],
    provides=["grant_verdict"],
    consumes=["tool_intent"],
    relates_to=["act.shape", "act.execute"],
)
class ActAuthorize(Node):
    """Grant check; stamps verdict onto the Intent."""

    name = "act.authorize"

    def execute(self, node, inputs):
        out_port = node.config.get("to", "authorized")
        intent_a = inputs.get(node.config.get("from", "intent"))
        content = _content(intent_a)
        allow = set(node.config.get("allow", []) or [])

        effect_kind = str(content.get("effect_kind") or "")
        tool = content.get("tool")

        if effect_kind == "no_effect":
            verdict = "skip"
        elif effect_kind in _BODY_NON_TOOL:
            verdict = "allow"
        elif effect_kind in _TOOL_KINDS:
            if tool in (None, "__none__"):
                verdict = "deny"
            elif tool in allow:
                verdict = "allow"
            else:
                verdict = "deny"
        else:
            verdict = "skip"

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
